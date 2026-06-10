"""
A2A Router — prompt-chained Agent 调度器。

机制（MD §3.0）：
  模型在输出末尾写 @review <内容>，外部正则扫描到后
  把 <内容> 作为消息派发给对应 Agent，形成"跨 Agent 接力"。
  这不是"Agent 自主路由"，是外部 30 行正则代码驱动的 prompt-chaining。

安全边界（MD §3.5）：
  MAX_A2A_DEPTH = 5
  MAX_MENTION_TARGETS = 2（单条消息最多 @2 个 Agent）
"""

import re
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage

from src.agent.registry import get_agent, get_default_agent, list_agent_ids

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
) -> AsyncGenerator[dict, None]:
    """
    主路由循环：
      1. 默认从 knowledge agent 开始
      2. 每轮流式运行当前 Agent，收集完整输出
      3. 解析输出中的 @mention，加入队列
      4. 循环直到队列空 或 深度超限

    产出带 agentId 的事件，与 BaseAgent.astream 相同格式。
    """
    # 用户显式 #tag 路由（Clowder 风格）
    tag_agent, cleaned_input = parse_user_tags(user_input)
    start_agent = tag_agent or "knowledge"
    queue: list[tuple[str, str]] = [(start_agent, cleaned_input)]
    depth = 0

    while queue and depth < MAX_A2A_DEPTH:
        agent_id, content = queue.pop(0)
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
        async for event in agent.astream([HumanMessage(content=content)], config):
            if event["type"] == "token":
                full_text += event["delta"]
            yield event  # 透传给 SSE

        # 解析下一跳
        mentions = parse_a2a_mentions(full_text, agent_id)
        queue.extend(mentions)
        depth += 1

    yield {"type": "done", "session_id": session_id}
