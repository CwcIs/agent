"""
A2A Router — prompt-chained Agent 调度器。

机制（MD §3.0）：
  模型在输出末尾写 @review <内容>，外部正则扫描到后
  把 <内容> 作为消息派发给对应 Agent，形成"跨 Agent 接力"。
  这不是"Agent 自主路由"，是外部 30 行正则代码驱动的 prompt-chaining。

context-transport（Phase 2）：
  A2A 交接时不再只传裸 mention 文本，而是通过 package_handoff()
  组装结构化上下文包（用户意图 + 工具结果 + Agent A 结论 + review 观点）。
  第一个 Agent 的历史通过 assemble_context() 按优先级 + token 预算裁剪，
  替代 Phase 1 的 naive LIMIT 20。

安全边界（MD §3.5）：
  MAX_A2A_DEPTH = 5
  MAX_MENTION_TARGETS = 2（单条消息最多 @2 个 Agent）
"""

import asyncio
import json
import re
import sqlite3
import uuid
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage

from src.agent.registry import get_agent, list_agent_ids
from src.agent.router_parser import (
    parse_user_tags,
    parse_a2a_mentions,
    detect_shadow_mentions,
)
from src.agent.verdict import detect_verdict
from src.agent.orchestrator import orchestrate_parallel
from src.agent.governance import (
    create_handoff_proposal,
    evaluate_handoff_proposal,
)
from src.agent.trace_events import record_agent_output_trace, record_tool_trace
from src.agent.worklist import save_handoff, mark_done, mark_failed, mark_running, get_pending
from src.context.assemble import assemble_context, package_handoff, agent_display_name
from src.lib.trace import content_fingerprint, record_trace_event, set_trace_context

_HISTORY_LIMIT = 20  # 保留兼容；assemble_context 使用 token 预算而非条数
MAX_A2A_DEPTH = 5


def _load_history(conn: sqlite3.Connection, session_id: str) -> list:
    """
    [DEPRECATED] 使用 assemble_context() 替代。
    保留此函数用于向后兼容和快速比对。
    """
    return assemble_context(conn, session_id)


def _save_message(
    conn: sqlite3.Connection,
    session_id: str,
    agent_id: str,
    role: str,
    content: str,
    message_id: str = "",
) -> str:
    persisted_id = message_id or str(uuid.uuid4())
    conn.execute(
        "INSERT INTO messages (id, session_id, agent_id, role, content) VALUES (?, ?, ?, ?, ?)",
        (persisted_id, session_id, agent_id, role, content),
    )
    conn.commit()
    return persisted_id


async def _route_serial_impl(
    user_input: str,
    session_id: str,
    conn: sqlite3.Connection | None = None,
    prompt_version: str = "v3",
    trace_id: str = "",
) -> AsyncGenerator[dict, None]:
    """
    主路由循环：
      1. 默认从 knowledge agent 开始
      2. 每轮流式运行当前 Agent，收集完整输出 + 工具调用事件
      3. 解析输出中的 @mention，通过 package_handoff() 组装上下文包
      4. 循环直到队列空 或 深度超限

    产出带 agentId 的事件，与 BaseAgent.astream 相同格式。
    """
    root_trace_id = trace_id or str(uuid.uuid4())
    user_message_id = str(uuid.uuid4())
    set_trace_context(root_trace_id, session_id=session_id, agent_id="router")
    record_trace_event(
        conn,
        "trace_start",
        trace_id=root_trace_id,
        session_id=session_id,
        agent_id="router",
        payload={
            "prompt_version": prompt_version,
            "input_chars": len(user_input),
        },
    )
    record_trace_event(
        conn,
        "input_received",
        trace_id=root_trace_id,
        session_id=session_id,
        agent_id="user",
        payload={
            "message_id": user_message_id,
            "content_preview": user_input[:1000],
            "content_sha256": content_fingerprint(user_input),
            "char_count": len(user_input),
            "truncated": len(user_input) > 1000,
        },
    )

    # 用户显式 #tag 路由（Clowder 风格）
    tag_agent, cleaned_input = parse_user_tags(user_input)
    start_agent = tag_agent or "knowledge"

    # ── Per-phase trace_id 追踪 ──
    # 每个 Agent phase 独立 trace_id，前端可按 phase 查看各自成本
    phase_trace_ids: dict[str, str] = {}

    # ── WorklistRegistry: 恢复上次 crash 遗留的 pending handoff ──
    if conn:
        pending_items = get_pending(conn, session_id)
        for item in pending_items:
            wid = item["id"]
            agent_id = item["agent_id"]
            agent = get_agent(agent_id)

            mark_running(conn, wid)

            if agent is None:
                mark_failed(conn, wid, f"Unknown agent: {agent_id}")
                yield {
                    "type": "error",
                    "agentId": agent_id,
                    "message": f"Resume failed: unknown agent '{agent_id}'",
                }
                continue

            resume_trace_id = str(uuid.uuid4())
            phase_trace_ids[agent_id] = resume_trace_id
            yield {"type": "agent_switch", "agentId": agent_id, "trace_id": resume_trace_id}
            set_trace_context(
                root_trace_id,
                phase_trace_id=resume_trace_id,
                session_id=session_id,
                agent_id=agent_id,
            )
            record_trace_event(
                conn,
                "agent_start",
                trace_id=root_trace_id,
                phase_trace_id=resume_trace_id,
                session_id=session_id,
                agent_id=agent_id,
                payload={"mode": "crash_recovery", "work_id": wid},
            )

            # 从 worklist 字段重建 handoff 上下文
            tool_events = json.loads(item["tool_events_json"])
            handoff_msgs = package_handoff(
                original_user_input=item["user_input"],
                agent_a_full_output=item["agent_a_output"],
                mention_content=item["mention_content"],
                tool_events=tool_events,
                agent_a_name=agent_display_name(item.get("agent_a_id") or "knowledge"),
            )

            config = {
                "configurable": {
                    "thread_id": f"{session_id}:{agent_id}:resume:{wid[:8]}",
                },
                "recursion_limit": 10,
            }

            agent.set_runtime_context(
                session_id,
                prompt_version,
                resume_trace_id,
                root_trace_id=root_trace_id,
            )

            resume_text = ""
            try:
                async for event in agent.astream(handoff_msgs, config):
                    if event["type"] == "token":
                        resume_text += event["delta"]
                    elif event["type"] in ("tool_start", "tool_end"):
                        record_trace_event(
                            conn,
                            event["type"],
                            trace_id=root_trace_id,
                            phase_trace_id=resume_trace_id,
                            session_id=session_id,
                            agent_id=agent_id,
                            name=event.get("name", "unknown"),
                            payload={
                                "tool_call_id": event.get("tool_call_id", ""),
                                "input": event.get("input", {}),
                                "result": event.get("result", "") if event["type"] == "tool_end" else "",
                            },
                        )
                    yield event
            except Exception as exc:
                mark_failed(conn, wid, str(exc))
                record_trace_event(
                    conn,
                    "error",
                    trace_id=root_trace_id,
                    phase_trace_id=resume_trace_id,
                    session_id=session_id,
                    agent_id=agent_id,
                    status="error",
                    name="crash_recovery",
                    payload={"message": str(exc), "work_id": wid},
                )
                yield {
                    "type": "error",
                    "agentId": agent_id,
                    "message": f"Resume error: {exc}",
                }
                continue

            if conn and resume_text:
                _save_message(conn, session_id, agent_id, "assistant", resume_text)

            mark_done(conn, wid)
            record_trace_event(
                conn,
                "agent_end",
                trace_id=root_trace_id,
                phase_trace_id=resume_trace_id,
                session_id=session_id,
                agent_id=agent_id,
                payload={
                    "mode": "crash_recovery",
                    "work_id": wid,
                    "output_chars": len(resume_text),
                    "output_sha256": content_fingerprint(resume_text),
                },
            )

    # 第一跳：通过 assemble_context 按优先级 + token 预算加载历史
    # 同时注入相关笔记（Context 改造 — Phase 4）
    history = assemble_context(conn, session_id, user_input=cleaned_input) if conn else []
    first_messages = history + [HumanMessage(content=cleaned_input)]
    record_trace_event(
        conn,
        "context_assembled",
        trace_id=root_trace_id,
        session_id=session_id,
        agent_id=start_agent,
        payload={
            "history_message_count": len(history),
            "final_message_count": len(first_messages),
            "explicit_route": tag_agent or "",
            "cleaned_input_chars": len(cleaned_input),
        },
    )

    # 持久化用户消息（在 assemble 之后，避免重复出现在历史中）
    if conn:
        _save_message(
            conn,
            session_id,
            "user",
            "user",
            user_input,
            message_id=user_message_id,
        )

    queue: list[tuple[str, list, str | None]] = [(start_agent, first_messages, None)]  # (agent_id, messages, work_id)
    depth = 0
    handoff_history: list = []  # verdict-detect: 记录每次 handoff 防 loop
    trace_status = "ok"
    final_verdict = "incomplete"

    while queue and depth < MAX_A2A_DEPTH:
        agent_id, messages, work_id = queue.pop(0)
        agent = get_agent(agent_id)

        if agent is None:
            trace_status = "error"
            final_verdict = "unknown_agent"
            if conn and work_id:
                mark_failed(conn, work_id, f"Unknown agent: {agent_id}")
            record_trace_event(
                conn,
                "error",
                trace_id=root_trace_id,
                session_id=session_id,
                agent_id=agent_id,
                status="error",
                name="unknown_agent",
                payload={"message": f"Unknown agent: {agent_id}", "depth": depth},
            )
            yield {
                "type": "error",
                "agentId": agent_id,
                "message": f"Unknown agent: {agent_id}",
            }
            break

        # ── WorklistRegistry: 标记开始执行 ──
        if conn and work_id:
            mark_running(conn, work_id)

        # ── Per-phase trace_id：每个 Agent 独立 trace，全局 trace_id 仅用于 session 关联 ──
        phase_trace_id = str(uuid.uuid4())
        phase_trace_ids[agent_id] = phase_trace_id
        set_trace_context(
            root_trace_id,
            phase_trace_id=phase_trace_id,
            session_id=session_id,
            agent_id=agent_id,
        )
        record_trace_event(
            conn,
            "agent_start",
            trace_id=root_trace_id,
            phase_trace_id=phase_trace_id,
            session_id=session_id,
            agent_id=agent_id,
            payload={
                "depth": depth,
                "message_count": len(messages),
                "work_id": work_id or "",
            },
        )

        # 切换 Agent 通知前端（携带本 phase 的 trace_id）
        if depth > 0:
            yield {"type": "agent_switch", "agentId": agent_id, "trace_id": phase_trace_id}

        config = {
            "configurable": {"thread_id": f"{session_id}:{agent_id}:{depth}"},
            "recursion_limit": 10,
        }

        agent.set_runtime_context(
            session_id,
            prompt_version,
            phase_trace_id,
            root_trace_id=root_trace_id,
        )

        full_text = ""
        tool_events: list[dict] = []  # 收集工具调用事件，用于后续 context-transport

        try:
            async for event in agent.astream(messages, config):
                if event["type"] == "token":
                    full_text += event["delta"]

                # 旁路收集工具事件（不改变 yield，不影响 SSE）
                elif event["type"] in ("tool_start", "tool_end"):
                    tool_events.append({
                        "type": event["type"],
                        "name": event.get("name"),
                        "input": event.get("input"),
                        "result": event.get("result"),
                    })

                    record_tool_trace(
                        conn,
                        root_trace_id=root_trace_id,
                        phase_trace_id=phase_trace_id,
                        session_id=session_id,
                        agent_id=agent_id,
                        event=event,
                    )

                    # 工具结果持久化到 DB，让后续请求也能看到历史工具结果
                    if event["type"] == "tool_end" and conn:
                        try:
                            _save_message(
                                conn, session_id, agent_id, "tool",
                                f"tool:{event.get('name', 'unknown')}:{event.get('result', '')}",
                            )
                        except Exception:
                            pass  # tool 消息持久化失败不阻塞主流程

                yield event  # 透传给 SSE

        except Exception as exc:
            trace_status = "error"
            final_verdict = "agent_error"
            if conn and work_id:
                mark_failed(conn, work_id, str(exc))
            record_trace_event(
                conn,
                "error",
                trace_id=root_trace_id,
                phase_trace_id=phase_trace_id,
                session_id=session_id,
                agent_id=agent_id,
                status="error",
                name="agent_execution",
                payload={"message": str(exc), "depth": depth},
            )
            record_trace_event(
                conn,
                "agent_end",
                trace_id=root_trace_id,
                phase_trace_id=phase_trace_id,
                session_id=session_id,
                agent_id=agent_id,
                status="error",
                payload={"depth": depth, "output_chars": len(full_text)},
            )
            yield {
                "type": "error",
                "agentId": agent_id,
                "message": f"Agent execution error: {exc}",
            }
            depth += 1
            continue  # 跳过 mention parsing，继续处理队列中下一个任务

        # 持久化 assistant 回复
        assistant_message_id = ""
        if conn and full_text:
            assistant_message_id = _save_message(
                conn, session_id, agent_id, "assistant", full_text
            )

        record_agent_output_trace(
            conn,
            root_trace_id=root_trace_id,
            phase_trace_id=phase_trace_id,
            session_id=session_id,
            agent_id=agent_id,
            full_text=full_text,
            message_id=assistant_message_id,
            tool_call_count=sum(
                1 for event in tool_events if event["type"] == "tool_end"
            ),
            depth=depth,
        )

        # ── WorklistRegistry: 标记当前任务完成 ──
        if conn and work_id:
            mark_done(conn, work_id)

        # 解析下一跳 — 使用 package_handoff 组装结构化上下文包
        agent_ids = list_agent_ids()

        mentions = parse_a2a_mentions(full_text, agent_id, agent_ids)

        # ── a2a-shadow-detection：只告警，不生成可执行任务 ──
        shadows = detect_shadow_mentions(full_text, agent_id, agent_ids)
        for sw in shadows:
            shadow_proposal = None
            shadow_decision = None
            if conn and sw.get("content"):
                shadow_proposal = create_handoff_proposal(
                    conn,
                    trace_id=root_trace_id,
                    phase_trace_id=phase_trace_id,
                    session_id=session_id,
                    source_agent_id=agent_id,
                    target_agent_id=sw["agent_id"],
                    objective=sw["content"],
                    depth=depth,
                    input_refs=[
                        f"trace:{root_trace_id}",
                        f"phase:{phase_trace_id}",
                    ],
                    trigger_type="shadow",
                )
                shadow_decision = evaluate_handoff_proposal(
                    conn,
                    shadow_proposal,
                    valid_agent_ids=agent_ids,
                    max_depth=MAX_A2A_DEPTH,
                )
                record_trace_event(
                    conn,
                    "handoff_proposed",
                    trace_id=root_trace_id,
                    phase_trace_id=phase_trace_id,
                    session_id=session_id,
                    agent_id=agent_id,
                    status="degraded",
                    name=sw["agent_id"],
                    payload={
                        "proposal_id": shadow_proposal["id"],
                        "proposal_hash": shadow_proposal["proposal_hash"],
                        "target_agent_id": sw["agent_id"],
                        "trigger_type": "shadow",
                    },
                )
                record_trace_event(
                    conn,
                    "policy_decision",
                    trace_id=root_trace_id,
                    phase_trace_id=phase_trace_id,
                    session_id=session_id,
                    agent_id="policy",
                    parent_agent_id=agent_id,
                    status=shadow_decision.outcome,
                    name=shadow_decision.effective_risk,
                    payload={
                        "proposal_id": shadow_proposal["id"],
                        "outcome": shadow_decision.outcome,
                        "reason": shadow_decision.reason,
                        "policy_version": shadow_decision.policy_version,
                    },
                )
            record_trace_event(
                conn,
                "warning",
                trace_id=root_trace_id,
                phase_trace_id=phase_trace_id,
                session_id=session_id,
                agent_id=agent_id,
                status="warning",
                name="shadow_mention",
                payload={
                    "message": sw["warning"],
                    "target_agent_id": sw.get("agent_id", ""),
                    "proposal_id": shadow_proposal["id"] if shadow_proposal else "",
                },
            )
            yield {
                "type": "warning",
                "agentId": agent_id,
                "message": sw["warning"],
                "shadow": True,
            }
        # ── verdict-detect：链路终止判定 ──
        verdict = detect_verdict(
            agent_full_text=full_text,
            mentions=mentions,
            current_agent_id=agent_id,
            depth=depth,
            max_depth=MAX_A2A_DEPTH,
            handoff_history=handoff_history,
        )

        if verdict.warning:
            record_trace_event(
                conn,
                "warning",
                trace_id=root_trace_id,
                phase_trace_id=phase_trace_id,
                session_id=session_id,
                agent_id=agent_id,
                status="warning",
                name="verdict_warning",
                payload={"message": verdict.warning},
            )
            yield {"type": "warning", "agentId": agent_id, "message": verdict.warning}

        record_trace_event(
            conn,
            "verdict",
            trace_id=root_trace_id,
            phase_trace_id=phase_trace_id,
            session_id=session_id,
            agent_id=agent_id,
            status="terminal" if verdict.should_terminate else "continue",
            name=verdict.reason,
            payload={
                "reason": verdict.reason,
                "should_terminate": verdict.should_terminate,
                "mention_targets": [target for target, _ in mentions],
                "depth": depth,
            },
        )

        if verdict.should_terminate:
            final_verdict = verdict.reason
            yield {"type": "verdict", "agentId": agent_id, "reason": verdict.reason}
            break

        # ── G2 Proposal Plane + Policy Plane ─────────────────────
        # mention 只表达 Agent 的建议；只有 allow 决策才能进入 Orchestrator。
        approved_mentions: list[tuple[str, str]] = []
        approved_proposal_ids: list[str] = []
        for next_agent_id, mention_content in mentions:
            if conn is None:
                yield {
                    "type": "warning",
                    "agentId": agent_id,
                    "message": "Handoff proposal could not be persisted; execution denied.",
                }
                continue

            proposal = create_handoff_proposal(
                conn,
                trace_id=root_trace_id,
                phase_trace_id=phase_trace_id,
                session_id=session_id,
                source_agent_id=agent_id,
                target_agent_id=next_agent_id,
                objective=mention_content,
                depth=depth,
                input_refs=[
                    f"trace:{root_trace_id}",
                    f"phase:{phase_trace_id}",
                ],
            )
            record_trace_event(
                conn,
                "handoff_proposed",
                trace_id=root_trace_id,
                phase_trace_id=phase_trace_id,
                session_id=session_id,
                agent_id=agent_id,
                name=next_agent_id,
                payload={
                    "proposal_id": proposal["id"],
                    "proposal_hash": proposal["proposal_hash"],
                    "target_agent_id": next_agent_id,
                    "requested_capabilities": proposal["requested_capabilities"],
                    "objective_preview": (
                        "[REDACTED:SENSITIVE_HANDOFF_OBJECTIVE]"
                        if proposal["data_sensitivity"] == "sensitive"
                        else mention_content[:500]
                    ),
                    "data_sensitivity": proposal["data_sensitivity"],
                },
            )
            decision = evaluate_handoff_proposal(
                conn,
                proposal,
                valid_agent_ids=agent_ids,
                max_depth=MAX_A2A_DEPTH,
            )
            record_trace_event(
                conn,
                "policy_decision",
                trace_id=root_trace_id,
                phase_trace_id=phase_trace_id,
                session_id=session_id,
                agent_id="policy",
                parent_agent_id=agent_id,
                status=decision.outcome,
                name=decision.effective_risk,
                payload={
                    "proposal_id": proposal["id"],
                    "outcome": decision.outcome,
                    "effective_risk": decision.effective_risk,
                    "reason": decision.reason,
                    "policy_version": decision.policy_version,
                },
            )
            if decision.allowed:
                approved_mentions.append((next_agent_id, mention_content))
                approved_proposal_ids.append(proposal["id"])
            else:
                message = (
                    f"Handoff to @{next_agent_id} stopped by Policy Gate: "
                    f"{decision.outcome} ({decision.reason})."
                )
                yield {
                    "type": "warning",
                    "agentId": agent_id,
                    "message": message,
                }

        if mentions and not approved_mentions:
            final_verdict = "handoff_blocked"
            trace_status = "warning"
            record_trace_event(
                conn,
                "verdict",
                trace_id=root_trace_id,
                phase_trace_id=phase_trace_id,
                session_id=session_id,
                agent_id=agent_id,
                status="terminal",
                name=final_verdict,
                payload={
                    "reason": final_verdict,
                    "should_terminate": True,
                    "mention_targets": [target for target, _ in mentions],
                    "depth": depth,
                },
            )
            yield {"type": "verdict", "agentId": agent_id, "reason": final_verdict}
            break

        mentions = approved_mentions

        # ── Execution Plane：单 mention 串行；多 mention 并行 fan-out ──
        tool_results = [e for e in tool_events if e["type"] == "tool_end"]

        if len(mentions) > 1:
            for (next_agent_id, mention_content), proposal_id in zip(
                mentions, approved_proposal_ids
            ):
                record_trace_event(
                    conn,
                    "handoff",
                    trace_id=root_trace_id,
                    phase_trace_id=phase_trace_id,
                    session_id=session_id,
                    agent_id=next_agent_id,
                    parent_agent_id=agent_id,
                    name="parallel",
                    payload={
                        "from_agent": agent_id,
                        "to_agent": next_agent_id,
                        "proposal_id": proposal_id,
                        "mention_preview": mention_content[:500],
                        "mention_sha256": content_fingerprint(mention_content),
                    },
                )
            # MultiMentionOrchestrator: 并行 fan-out，不继续链式传递
            # 先为每个 parallel mention 创建 worklist 条目，保证 crash recovery
            parallel_wids: list[str] = []
            if conn:
                for (next_agent_id, mention_content), proposal_id in zip(
                    mentions, approved_proposal_ids
                ):
                    wid = save_handoff(
                        conn, session_id, next_agent_id, depth,
                        user_input, full_text, mention_content, tool_results,
                        agent_a_id=agent_id,
                        proposal_id=proposal_id,
                    )
                    parallel_wids.append(wid)
            # 每个并行 branch 独立 trace_id
            parallel_trace_ids = [str(uuid.uuid4()) for _ in mentions]
            for (next_agent_id, _), btid in zip(mentions, parallel_trace_ids):
                phase_trace_ids[next_agent_id] = btid
            async for event in orchestrate_parallel(
                user_input=user_input,
                mentions=mentions,
                agent_a_full_output=full_text,
                tool_events=tool_results,
                session_id=session_id,
                conn=conn,
                worklist_ids=parallel_wids if parallel_wids else None,
                prompt_version=prompt_version,
                agent_a_id=agent_id,
                trace_ids=parallel_trace_ids,
                root_trace_id=root_trace_id,
            ):
                if event.get("type") == "error":
                    trace_status = "error"
                    final_verdict = "parallel_error"
                yield event
            if final_verdict != "parallel_error":
                final_verdict = "parallel_complete"
            break  # 并行 branches 结束后不继续串行链路

        for (next_agent_id, mention_content), proposal_id in zip(
            mentions, approved_proposal_ids
        ):
            record_trace_event(
                conn,
                "handoff",
                trace_id=root_trace_id,
                phase_trace_id=phase_trace_id,
                session_id=session_id,
                agent_id=next_agent_id,
                parent_agent_id=agent_id,
                name="serial",
                payload={
                    "from_agent": agent_id,
                    "to_agent": next_agent_id,
                    "proposal_id": proposal_id,
                    "mention_preview": mention_content[:500],
                    "mention_sha256": content_fingerprint(mention_content),
                },
            )
            handoff_msgs = package_handoff(
                original_user_input=user_input,
                agent_a_full_output=full_text,
                mention_content=mention_content,
                tool_events=tool_results,
                agent_a_name=agent_display_name(agent_id),
            )
            wid = None
            if conn:
                wid = save_handoff(
                    conn, session_id, next_agent_id, depth,
                    user_input, full_text, mention_content, tool_results,
                    agent_a_id=agent_id,
                    proposal_id=proposal_id,
                )
            queue.append((next_agent_id, handoff_msgs, wid))
        depth += 1

    if queue and depth >= MAX_A2A_DEPTH:
        final_verdict = "max_depth_reached"
        trace_status = "warning"

    set_trace_context(root_trace_id, session_id=session_id, agent_id="router")
    record_trace_event(
        conn,
        "trace_end",
        trace_id=root_trace_id,
        session_id=session_id,
        agent_id="router",
        status=trace_status,
        name=final_verdict,
        payload={
            "verdict": final_verdict,
            "depth": depth,
            "phase_trace_ids": phase_trace_ids,
        },
    )
    yield {
        "type": "done",
        "session_id": session_id,
        "trace_id": root_trace_id,
        "phase_trace_ids": phase_trace_ids,
    }


async def route_serial(
    user_input: str,
    session_id: str,
    conn: sqlite3.Connection | None = None,
    prompt_version: str = "v3",
    trace_id: str = "",
) -> AsyncGenerator[dict, None]:
    """Public router wrapper that always closes the root trace on failure."""
    root_trace_id = trace_id or str(uuid.uuid4())
    completed = False
    try:
        async for event in _route_serial_impl(
            user_input,
            session_id,
            conn=conn,
            prompt_version=prompt_version,
            trace_id=root_trace_id,
        ):
            if event.get("type") == "done":
                completed = True
            yield event
    except asyncio.CancelledError:
        set_trace_context(root_trace_id, session_id=session_id, agent_id="router")
        record_trace_event(
            conn,
            "warning",
            trace_id=root_trace_id,
            session_id=session_id,
            agent_id="router",
            status="warning",
            name="client_cancelled",
            payload={"message": "Client disconnected or cancelled the stream"},
        )
        if not completed:
            record_trace_event(
                conn,
                "trace_end",
                trace_id=root_trace_id,
                session_id=session_id,
                agent_id="router",
                status="cancelled",
                name="client_cancelled",
                payload={"verdict": "client_cancelled"},
            )
        raise
    except Exception as exc:
        set_trace_context(root_trace_id, session_id=session_id, agent_id="router")
        record_trace_event(
            conn,
            "error",
            trace_id=root_trace_id,
            session_id=session_id,
            agent_id="router",
            status="error",
            name="unhandled_exception",
            payload={"message": str(exc)},
        )
        if not completed:
            record_trace_event(
                conn,
                "trace_end",
                trace_id=root_trace_id,
                session_id=session_id,
                agent_id="router",
                status="error",
                name="unhandled_exception",
                payload={"verdict": "unhandled_exception"},
            )
        yield {
            "type": "error",
            "agentId": "router",
            "message": f"Routing failed: {exc}",
            "trace_id": root_trace_id,
        }
