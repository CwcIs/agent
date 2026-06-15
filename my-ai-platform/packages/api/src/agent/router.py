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
from src.agent.worklist import save_handoff, mark_done, mark_failed, mark_running, get_pending
from src.context.assemble import assemble_context, package_handoff

_HISTORY_LIMIT = 20  # 保留兼容；assemble_context 使用 token 预算而非条数
MAX_A2A_DEPTH = 5


def _load_history(conn: sqlite3.Connection, session_id: str) -> list:
    """
    [DEPRECATED] 使用 assemble_context() 替代。
    保留此函数用于向后兼容和快速比对。
    """
    return assemble_context(conn, session_id)


def _save_message(conn: sqlite3.Connection, session_id: str, agent_id: str, role: str, content: str) -> None:
    conn.execute(
        "INSERT INTO messages (id, session_id, agent_id, role, content) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), session_id, agent_id, role, content),
    )
    conn.commit()


async def route_serial(
    user_input: str,
    session_id: str,
    conn: sqlite3.Connection | None = None,
) -> AsyncGenerator[dict, None]:
    """
    主路由循环：
      1. 默认从 knowledge agent 开始
      2. 每轮流式运行当前 Agent，收集完整输出 + 工具调用事件
      3. 解析输出中的 @mention，通过 package_handoff() 组装上下文包
      4. 循环直到队列空 或 深度超限

    产出带 agentId 的事件，与 BaseAgent.astream 相同格式。
    """
    # 用户显式 #tag 路由（Clowder 风格）
    tag_agent, cleaned_input = parse_user_tags(user_input)
    start_agent = tag_agent or "knowledge"

    # 持久化用户消息
    if conn:
        _save_message(conn, session_id, "user", "user", user_input)

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

            yield {"type": "agent_switch", "agentId": agent_id}

            # 从 worklist 字段重建 handoff 上下文
            tool_events = json.loads(item["tool_events_json"])
            handoff_msgs = package_handoff(
                original_user_input=item["user_input"],
                agent_a_full_output=item["agent_a_output"],
                mention_content=item["mention_content"],
                tool_events=tool_events,
            )

            config = {
                "configurable": {
                    "thread_id": f"{session_id}:{agent_id}:resume:{wid[:8]}",
                },
                "recursion_limit": 10,
            }

            resume_text = ""
            try:
                async for event in agent.astream(handoff_msgs, config):
                    if event["type"] == "token":
                        resume_text += event["delta"]
                    yield event
            except Exception as exc:
                mark_failed(conn, wid, str(exc))
                yield {
                    "type": "error",
                    "agentId": agent_id,
                    "message": f"Resume error: {exc}",
                }
                continue

            if conn and resume_text:
                _save_message(conn, session_id, agent_id, "assistant", resume_text)

            mark_done(conn, wid)

    # 第一跳：通过 assemble_context 按优先级 + token 预算加载历史
    history = assemble_context(conn, session_id)[:-1] if conn else []  # 去掉刚存的那条用户消息
    first_messages = history + [HumanMessage(content=cleaned_input)]

    queue: list[tuple[str, list, str | None]] = [(start_agent, first_messages, None)]  # (agent_id, messages, work_id)
    depth = 0
    handoff_history: list = []  # verdict-detect: 记录每次 handoff 防 loop

    while queue and depth < MAX_A2A_DEPTH:
        agent_id, messages, work_id = queue.pop(0)
        agent = get_agent(agent_id)

        if agent is None:
            if conn and work_id:
                mark_failed(conn, work_id, f"Unknown agent: {agent_id}")
            yield {
                "type": "error",
                "agentId": agent_id,
                "message": f"Unknown agent: {agent_id}",
            }
            break

        # ── WorklistRegistry: 标记开始执行 ──
        if conn and work_id:
            mark_running(conn, work_id)

        # 切换 Agent 通知前端
        if depth > 0:
            yield {"type": "agent_switch", "agentId": agent_id}

        config = {
            "configurable": {"thread_id": f"{session_id}:{agent_id}:{depth}"},
            "recursion_limit": 10,
        }

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
            if conn and work_id:
                mark_failed(conn, work_id, str(exc))
            yield {
                "type": "error",
                "agentId": agent_id,
                "message": f"Agent execution error: {exc}",
            }
            depth += 1
            continue  # 跳过 mention parsing，继续处理队列中下一个任务

        # 持久化 assistant 回复
        if conn and full_text:
            _save_message(conn, session_id, agent_id, "assistant", full_text)

        # ── WorklistRegistry: 标记当前任务完成 ──
        if conn and work_id:
            mark_done(conn, work_id)

        # 解析下一跳 — 使用 package_handoff 组装结构化上下文包
        agent_ids = list_agent_ids()

        mentions = parse_a2a_mentions(full_text, agent_id, agent_ids)

        # ── a2a-shadow-detection：行内 @mention 扫描 ──
        shadows = detect_shadow_mentions(full_text, agent_id, agent_ids)
        for sw in shadows:
            yield {
                "type": "warning",
                "agentId": agent_id,
                "message": sw["warning"],
                "shadow": True,
            }
            # 如果主解析没找到 mention，把 shadow mention 加入队列
            if not mentions and sw["content"]:
                mentions.append((sw["agent_id"], sw["content"]))

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
            yield {"type": "warning", "agentId": agent_id, "message": verdict.warning}

        if verdict.should_terminate:
            yield {"type": "verdict", "agentId": agent_id, "reason": verdict.reason}
            break

        # ── 路由决策：单 mention → 串行入队；多 mention → 并行 fan-out ──
        tool_results = [e for e in tool_events if e["type"] == "tool_end"]

        if len(mentions) > 1:
            # MultiMentionOrchestrator: 并行 fan-out，不继续链式传递
            async for event in orchestrate_parallel(
                user_input=user_input,
                mentions=mentions,
                agent_a_full_output=full_text,
                tool_events=tool_results,
                session_id=session_id,
            ):
                yield event
            break  # 并行 branches 结束后不继续串行链路

        for next_agent_id, mention_content in mentions:
            handoff_msgs = package_handoff(
                original_user_input=user_input,
                agent_a_full_output=full_text,
                mention_content=mention_content,
                tool_events=tool_results,
            )
            wid = None
            if conn:
                wid = save_handoff(
                    conn, session_id, next_agent_id, depth,
                    user_input, full_text, mention_content, tool_results,
                )
            queue.append((next_agent_id, handoff_msgs, wid))
        depth += 1

    yield {"type": "done", "session_id": session_id}
