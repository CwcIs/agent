"""
MultiMentionOrchestrator — 多 Agent 并行调度器。

当一条消息包含多个 @mention 目标时（最多 MAX_MENTION_TARGETS=2），
把每个目标 Agent 并行执行，流式输出 interleaved SSE 事件。

对应 Clowder 的 MultiMentionOrchestrator.ts。
Phase 3 锚点 #1。

与 route_serial 的关系：
  route_serial: 单 @mention → 串行 A→B→C 链路
  orchestrator: 多 @mention → 并行 fan-out，不继续链式传递

安全边界（MD §3.5）：
  MAX_MENTION_TARGETS = 2 — 单条消息最多 @ 两个 Agent
"""

import asyncio
import sqlite3
import uuid
from typing import AsyncGenerator

from src.agent.registry import get_agent
from src.agent.worklist import mark_done as wl_mark_done, mark_failed as wl_mark_failed
from src.context.assemble import package_handoff


def _save_message(conn: sqlite3.Connection, session_id: str, agent_id: str, role: str, content: str) -> None:
    conn.execute(
        "INSERT INTO messages (id, session_id, agent_id, role, content) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), session_id, agent_id, role, content),
    )
    conn.commit()


async def _run_one_agent(
    agent_id: str,
    content: str,
    user_input: str,
    agent_a_output: str,
    tool_events: list[dict],
    session_id: str,
    event_queue: asyncio.Queue,
    conn: sqlite3.Connection | None = None,
    work_id: str = "",
    prompt_version: str = "v1",
) -> None:
    """
    在独立 task 中运行一个 Agent，把事件推入共享队列。
    结束时推入 None sentinel 通知调用者。

    如果提供 conn + work_id，会在执行完成后：
      - 将 assistant 回复持久化到 messages 表
      - 将 worklist 项标记为 done/failed
    """
    try:
        agent = get_agent(agent_id)
        if agent is None:
            await event_queue.put({
                "type": "error",
                "agentId": agent_id,
                "message": f"Unknown agent: {agent_id}",
            })
            if conn and work_id:
                wl_mark_failed(conn, work_id, f"Unknown agent: {agent_id}")
            return

        messages = package_handoff(
            original_user_input=user_input,
            agent_a_full_output=agent_a_output,
            mention_content=content,
            tool_events=tool_events,
        )

        config = {
            "configurable": {
                "thread_id": f"{session_id}:{agent_id}:parallel:{uuid.uuid4().hex[:8]}",
            },
            "recursion_limit": 10,
        }

        agent.set_runtime_context(session_id, prompt_version)

        full_text = ""
        async for event in agent.astream(messages, config):
            if event.get("type") == "done":
                continue  # 抑制个体 done，由 orchestrator 统一下发
            if event.get("type") == "token":
                full_text += event.get("delta", "")
            await event_queue.put(event)

        # 持久化 assistant 回复 + 标记 worklist done
        if conn and full_text:
            _save_message(conn, session_id, agent_id, "assistant", full_text)
        if conn and work_id:
            wl_mark_done(conn, work_id)

    except Exception as exc:
        if conn and work_id:
            wl_mark_failed(conn, work_id, str(exc))
        await event_queue.put({
            "type": "error",
            "agentId": agent_id,
            "message": str(exc),
        })
    finally:
        await event_queue.put(None)  # sentinel: 这个 agent 跑完了


async def orchestrate_parallel(
    user_input: str,
    mentions: list[tuple[str, str]],
    agent_a_full_output: str,
    tool_events: list[dict],
    session_id: str,
    conn: sqlite3.Connection | None = None,
    worklist_ids: list[str] | None = None,
    prompt_version: str = "v1",
) -> AsyncGenerator[dict, None]:
    """
    并行 fan-out：把多个 mention 目标 Agent 同时跑起来，interleave 输出。

    参数：
      user_input          — 用户原始输入
      mentions            — [(agent_id, content), ...]，最多 MAX_MENTION_TARGETS 条
      agent_a_full_output — Agent A（trigger agent）的完整输出
      tool_events         — Agent A 的工具调用事件列表
      session_id          — 会话 id
      conn                — 数据库连接（用于持久化 assistant 回复 + worklist 状态）
      worklist_ids        — 每个 mention 对应的 worklist id（与 mentions 顺序一致）
      prompt_version      — prompt 版本标识

    产出：SSE-ready 事件 dict，与 BaseAgent.astream 格式相同。
          每个事件都带 agentId 字段，前端按 agentId 区分来源。
          最后的 done 事件由 orchestrator 统一下发。
    """
    event_queue: asyncio.Queue = asyncio.Queue()
    n_agents = len(mentions)
    wids = worklist_ids or [""] * n_agents

    # 启动所有 Agent（asyncio.Task，同一 event loop 上并发）
    tasks = [
        asyncio.create_task(
            _run_one_agent(
                agent_id=agent_id,
                content=content,
                user_input=user_input,
                agent_a_output=agent_a_full_output,
                tool_events=tool_events,
                session_id=session_id,
                event_queue=event_queue,
                conn=conn,
                work_id=wids[i],
                prompt_version=prompt_version,
            )
        )
        for i, (agent_id, content) in enumerate(mentions)
    ]

    # 收集事件直到所有 Agent 完成
    finished = 0
    while finished < n_agents:
        event = await event_queue.get()
        if event is None:
            finished += 1
        else:
            yield event

    # 等待所有 task 清理完成（不应抛异常，已在 _run_one_agent 内捕获）
    await asyncio.gather(*tasks, return_exceptions=True)
