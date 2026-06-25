# ============================================================
# Context Assembler — 三层记忆组装 + A2A 上下文裁剪
# 对应 MD §4.4 记忆三层架构
#
# 分层逻辑在 Assembler，不在 Store（MD §4.4 重要修正）：
#   Clowder 的 RedisMessageStore.ts 只是底层存储后端，
#   真正的分层逻辑在 ContextAssembler.ts + context-transport.ts
#
# 三层（MD §4.4 表）：
#   工作记忆 — 最近 N 轮对话（SQLite messages 表，按优先级 + token 预算裁剪）
#   情节记忆 — 笔记 + 历史（Agent tool call 时拉取，不做自动注入）
#   语义记忆 — 向量检索（sqlite-vec + sentence-transformers，通过 search_notes 调用）
#
# 两个主要函数：
#   assemble_context()   — 第一个 Agent 启动前，从 DB 按优先级组装历史
#   package_handoff()     — Agent A → Agent B 交接时，组装结构化上下文包
#
# 核心改进（vs Phase 1 的 naive LIMIT 20）：
#   1. 用户消息 HIGH 优先级，永不被裁剪
#   2. 长叙事助理消息 LOW 优先级，先被丢弃
#   3. 被丢弃的消息生成一句话摘要，不让 Agent B 完全失明
#   4. A2A 交接包包含：用户意图 + 工具结果 + Agent A 结论 + review 观点
#
# 注意（MD §4.6）：
#   sessionId + promptVersion 一起贯穿 → system prompt 拼接时带版本号
# ============================================================

import re
import sqlite3
from typing import Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

# ============================================================
# Constants
# ============================================================
FIRST_HOP_BUDGET_TOKENS = 3000    # 第一个 Agent 的历史 token 上限
HANDOFF_BUDGET_TOKENS = 1500      # A2A 交接包的 token 上限
FACT_SECTION_BUDGET_RATIO = 0.4   # 事实段最多占 40% 预算
CONCLUSION_SECTION_BUDGET_RATIO = 0.5  # 结论段最多占 50% 预算
SHORT_MSG_THRESHOLD = 200          # 短消息阈值（字符数）

# agent_id → 中文显示名
_AGENT_DISPLAY_NAMES: dict[str, str] = {
    "knowledge": "Knowledge Agent",
    "review": "Review Agent",
    "brain": "Brain Agent",
}


def agent_display_name(agent_id: str) -> str:
    """返回 Agent 的中文显示名，未知 agent_id 退化为 '{agent_id} Agent'。"""
    return _AGENT_DISPLAY_NAMES.get(agent_id, f"{agent_id} Agent")


# ============================================================
# Token Estimation
# ============================================================

def estimate_tokens(text: str) -> int:
    """保守估算 token 数。混合中英文约 2.5 字符/token。"""
    if not text:
        return 0
    return max(1, int(len(text) / 2.5))


def _estimate_message_tokens(msg: BaseMessage) -> int:
    """估算单条 LangChain 消息的 token 数。"""
    content = msg.content if hasattr(msg, 'content') else str(msg)
    if isinstance(content, str):
        return estimate_tokens(content)
    if isinstance(content, list):
        # 多模态 content（图片等），只算文本部分
        return sum(estimate_tokens(part.get("text", "")) for part in content if isinstance(part, dict))
    return estimate_tokens(str(content))


# ============================================================
# Message Priority Classification
# ============================================================

def _priority(msg: BaseMessage) -> str:
    """判断消息保留优先级：HIGH > MEDIUM > LOW"""
    if isinstance(msg, HumanMessage):
        return "HIGH"
    if isinstance(msg, AIMessage):
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if len(content) < SHORT_MSG_THRESHOLD:
            return "MEDIUM"   # 短助理消息（可能是直接回答或简短确认）
        if "@" in content:
            return "MEDIUM"   # 含 @mention（可能是交接消息）
        return "LOW"          # 长叙事，优先丢弃
    # tool 消息
    return "MEDIUM"


# ============================================================
# Drop Summary
# ============================================================

def _build_drop_summary(dropped: list[BaseMessage]) -> Optional[str]:
    """为被丢弃的消息生成一句话摘要，让后续 Agent 不完全失明。"""
    if not dropped:
        return None

    user_inputs = []
    for m in dropped:
        if isinstance(m, HumanMessage):
            content = m.content if isinstance(m.content, str) else str(m.content)
            user_inputs.append(content[:60])

    if user_inputs:
        return f"之前聊过：{'；'.join(user_inputs[:3])}"
    return "之前有过几轮对话"


# ============================================================
# First-Hop History Assembly
# ============================================================

def assemble_context(
    conn: sqlite3.Connection,
    session_id: str,
    budget_tokens: int = FIRST_HOP_BUDGET_TOKENS,
) -> list[BaseMessage]:
    """
    从 DB 加载对话历史，按优先级 + token 预算裁剪。

    算法：
      1. 从 messages 表按时间正序取当前 session 的所有消息
      2. 反向遍历（从最新到最旧），按优先级填充 token 预算
      3. HIGH（用户消息）永不被裁剪；MEDIUM 填满预算；LOW 先被丢弃
      4. 如果丢了消息，在开头插入一句话摘要

    返回 LangChain 消息列表（不包含当前用户输入，由 router 追加）。
    """
    if not conn:
        return []

    rows = conn.execute(
        "SELECT role, content FROM messages "
        "WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()

    if not rows:
        return []

    all_msgs: list[BaseMessage] = []
    for role, content in rows:
        if role == "user":
            all_msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            all_msgs.append(AIMessage(content=content))
        elif role == "tool":
            # tool 消息前缀标注，方便 Agent 理解
            all_msgs.append(AIMessage(content=f"[工具结果] {content}"))
        # 忽略其他 role

    # 反向遍历，按优先级填充
    kept: list[BaseMessage] = []
    used = 0
    dropped: list[BaseMessage] = []

    for msg in reversed(all_msgs):
        pri = _priority(msg)
        cost = _estimate_message_tokens(msg)

        if pri == "HIGH":
            # 用户消息永远保留（携带意图和约束）
            kept.insert(0, msg)
            used += cost
        elif used + cost <= budget_tokens:
            kept.insert(0, msg)
            used += cost
        else:
            dropped.insert(0, msg)

    # 如果有消息被丢弃，在开头插入摘要
    summary = _build_drop_summary(dropped)
    if summary:
        kept.insert(0, HumanMessage(content=f"[对话摘要] {summary}"))

    return kept


# ============================================================
# A2A Handoff Packaging
# ============================================================

# 匹配行首 @agent，用于从 Agent 输出中剥离 mention 行
_MENTION_LINE_RE = re.compile(r"^@([a-zA-Z][a-zA-Z0-9_-]*)\s*.*$", re.MULTILINE)


def _strip_mentions(text: str) -> str:
    """移除文本中的 @agent 行，保留其余内容。"""
    cleaned = _MENTION_LINE_RE.sub("", text).strip()
    # 清理多余空行
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _truncate_by_tokens(text: str, max_tokens: int) -> str:
    """按 token 预算截断文本，末尾加省略标记。"""
    if estimate_tokens(text) <= max_tokens:
        return text
    # 二分找截断点
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        if estimate_tokens(text[:mid]) <= max_tokens:
            lo = mid + 1
        else:
            hi = mid
    return text[:max(0, lo - 10)] + "\n\n[因上下文限制，后续内容略去]"


def package_handoff(
    original_user_input: str,
    agent_a_full_output: str,
    mention_content: str,
    tool_events: list[dict],
    budget_tokens: int = HANDOFF_BUDGET_TOKENS,
    agent_a_name: str = "Knowledge Agent",
) -> list[BaseMessage]:
    """
    为 A2A 交接组装结构化上下文包。

    段优先级（从高到低）：
      1. 用户意图 — 始终包含
      2. 已发现的事实 — 上限 40% 预算
      3. Agent A 的结论 — 上限 50% 预算
      4. 需要 Review 的观点 — 始终包含

    agent_a_name: 触发 handoff 的 Agent 显示名，用于 Section 3 header。
    tool_events 格式：[{"type": "tool_end", "name": "...", "result": "..."}, ...]

    返回 [HumanMessage(content=formatted_package)]。
    """
    sections: list[str] = []
    used = 0

    # ── Section 1: 用户意图（必含） ──
    intent_text = f"## 用户意图\n{original_user_input}"
    sections.append(intent_text)
    used += estimate_tokens(intent_text)

    # ── Section 2: 已发现的事实（上限 40%） ──
    if tool_events:
        facts_budget = int(budget_tokens * FACT_SECTION_BUDGET_RATIO)
        facts_header = "\n\n## 已发现的事实"
        facts_body_parts: list[str] = []
        facts_used = 0

        for evt in tool_events:
            if evt.get("type") != "tool_end":
                continue
            name = evt.get("name", "unknown")
            result = evt.get("result", "")
            chunk = f"\n\n[工具 {name}]\n{result}"
            chunk_cost = estimate_tokens(chunk)
            if facts_used + chunk_cost <= facts_budget:
                facts_body_parts.append(chunk)
                facts_used += chunk_cost

        if facts_body_parts:
            facts_section = facts_header + "".join(facts_body_parts)
            sections.append(facts_section)
            used += estimate_tokens(facts_section)

    # ── Section 3: Agent A 的结论（上限 50%） ──
    conclusion_budget = int(budget_tokens * CONCLUSION_SECTION_BUDGET_RATIO)
    conclusion = _strip_mentions(agent_a_full_output).strip()
    if conclusion:
        remaining = budget_tokens - used
        eff_budget = min(conclusion_budget, max(0, remaining - 100))
        if eff_budget > 0:
            trimmed = _truncate_by_tokens(conclusion, eff_budget)
            sections.append(f"\n\n## {agent_a_name} 的分析\n{trimmed}")
            used += estimate_tokens(trimmed)

    # ── Section 4: 需要 Review 的观点（必含） ──
    handoff = mention_content or agent_a_full_output
    sections.append(f"\n\n## 需要 Review 的观点\n{handoff}")

    full_text = "".join(sections)
    return [HumanMessage(content=full_text)]
