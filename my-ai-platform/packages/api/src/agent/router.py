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

import re
import sqlite3
import uuid
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage

from src.agent.registry import get_agent, list_agent_ids
from src.agent.verdict import detect_verdict
from src.context.assemble import assemble_context, package_handoff

_HISTORY_LIMIT = 20  # 保留兼容；assemble_context 使用 token 预算而非条数


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

MAX_A2A_DEPTH = 5
MAX_MENTION_TARGETS = 2

# 匹配行首 @agent_id，后接可选空格和观点文本
# 例：@review 早期创业不该做 ToC
_MENTION_RE = re.compile(
    r"(?:^|\n)[ \t]*@([a-zA-Z][a-zA-Z0-9_-]*)(?:[ \t]+(.+))?",
    re.MULTILINE,
)

# 匹配用户输入中的 #tag，例：#review
_TAG_RE = re.compile(r"#([a-zA-Z][a-zA-Z0-9_-]*)", re.IGNORECASE)

# 已知的 hashtag → agent_id 映射（Clowder 风格显式路由）
_TAG_AGENT_MAP = {
    "review": "review",
    "critique": "review",
}


def parse_user_tags(text: str) -> tuple[str | None, str]:
    """
    解析用户输入中的 #tag，返回 (agent_id, stripped_text)。
    只取第一个命中的 tag。未命中返回 (None, original_text)。
    """
    for m in _TAG_RE.finditer(text):
        tag = m.group(1).lower()
        if tag in _TAG_AGENT_MAP:
            stripped = _TAG_RE.sub("", text).strip()
            return _TAG_AGENT_MAP[tag], stripped
    return None, text


def parse_a2a_mentions(text: str, current_agent_id: str) -> list[tuple[str, str]]:
    """
    从 Agent 输出文本中解析 @mention。
    返回 [(agent_id, content), ...] 列表，最多 MAX_MENTION_TARGETS 条。
    - 过滤掉不存在的 Agent
    - 过滤掉自调用（Agent 不能 @自己）
    - 跳过 fenced code block 内的 @mention
    """
    # 剥除 fenced code blocks
    clean = re.sub(r"```.*?```", "", text, flags=re.DOTALL)

    valid_ids = set(list_agent_ids())
    results = []

    for m in _MENTION_RE.finditer(clean):
        agent_id = m.group(1).lower()
        content = (m.group(2) or "").strip()

        if agent_id == current_agent_id:
            continue
        if agent_id not in valid_ids:
            continue

        results.append((agent_id, content))
        if len(results) >= MAX_MENTION_TARGETS:
            break

    return results


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

    # 第一跳：通过 assemble_context 按优先级 + token 预算加载历史
    history = assemble_context(conn, session_id)[:-1] if conn else []  # 去掉刚存的那条用户消息
    first_messages = history + [HumanMessage(content=cleaned_input)]

    queue: list[tuple[str, list]] = [(start_agent, first_messages)]
    depth = 0
    handoff_history: list = []  # verdict-detect: 记录每次 handoff 防 loop

    while queue and depth < MAX_A2A_DEPTH:
        agent_id, messages = queue.pop(0)
        agent = get_agent(agent_id)

        if agent is None:
            yield {
                "type": "error",
                "agentId": agent_id,
                "message": f"Unknown agent: {agent_id}",
            }
            break

        # 切换 Agent 通知前端
        if depth > 0:
            yield {"type": "agent_switch", "agentId": agent_id}

        config = {
            "configurable": {"thread_id": f"{session_id}:{agent_id}:{depth}"},
            "recursion_limit": 10,
        }

        full_text = ""
        tool_events: list[dict] = []  # 收集工具调用事件，用于后续 context-transport

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

        # 持久化 assistant 回复
        if conn and full_text:
            _save_message(conn, session_id, agent_id, "assistant", full_text)

        # 解析下一跳 — 使用 package_handoff 组装结构化上下文包
        mentions = parse_a2a_mentions(full_text, agent_id)

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

        for next_agent_id, mention_content in mentions:
            handoff_msgs = package_handoff(
                original_user_input=user_input,
                agent_a_full_output=full_text,
                mention_content=mention_content,
                tool_events=[e for e in tool_events if e["type"] == "tool_end"],
            )
            queue.append((next_agent_id, handoff_msgs))
        depth += 1

    yield {"type": "done", "session_id": session_id}
