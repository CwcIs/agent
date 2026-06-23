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
import uuid
from typing import AsyncGenerator

from src.agent.registry import get_agent
from src.context.assemble import package_handoff


async def _run_one_agent(
    agent_id: str,
    content: str,
    user_input: str,
    agent_a_output: str,
    tool_events: list[dict],
    session_id: str,
    event_queue: asyncio.Queue,
) -> None:
    """
    在独立 task 中运行一个 Agent，把事件推入共享队列。
    结束时推入 None sentinel 通知调用者。
    """
    try:
        agent = get_agent(agent_id)
        if agent is None:
            await event_queue.put({
                "type": "error",
                "agentId": agent_id,
                "message": f"Unknown agent: {agent_id}",
            })
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

        async for event in agent.astream(messages, config):
            if event.get("type") == "done":
                continue  # 抑制个体 done，由 orchestrator 统一下发
            await event_queue.put(event)

    except Exception as exc:
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
) -> AsyncGenerator[dict, None]:
    """
    并行 fan-out：把多个 mention 目标 Agent 同时跑起来，interleave 输出。

    参数：
      user_input          — 用户原始输入
      mentions            — [(agent_id, content), ...]，最多 MAX_MENTION_TARGETS 条
      agent_a_full_output — Agent A（trigger agent）的完整输出
      tool_events         — Agent A 的工具调用事件列表
      session_id          — 会话 id

    产出：SSE-ready 事件 dict，与 BaseAgent.astream 格式相同。
          每个事件都带 agentId 字段，前端按 agentId 区分来源。
          最后的 done 事件由 orchestrator 统一下发。
    """
    event_queue: asyncio.Queue = asyncio.Queue()
    n_agents = len(mentions)

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
            )
        )
        for agent_id, content in mentions
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
