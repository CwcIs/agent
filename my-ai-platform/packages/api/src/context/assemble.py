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
# assemble_context() 分层触发算法（v3 升级 — CC 五层金字塔）：
#   每次强制 L1（大文件卸载，零成本）
#   → 总 token ≤ budget：原样返回（零成本）
#   → 总 token ≤ budget × 1.5：只做 burst 保留（轻量，不摘要）
#   → 总 token > budget × 1.5：完整三阶段（burst + anchor + tombstone，L5 昂贵操作）
#
#   Phase 1 — Burst Detection：从最新消息往回找 >=15 分钟静默缺口，
#             保证最近一个对话 burst 完整保留（最多 12 条，最少 4 条）。
#             语义链保护：burst 首条若为 tool 消息，向前扩展包含对应 assistant。
#   Phase 2 — Anchor Selection：对省略消息做重要性评分，选 top 3 锚点。
#   Phase 3 — Tombstone：对省略消息生成墓碑摘要，让 Agent 知道有信息被省略。
#
# 注意（MD §4.6）：
#   sessionId + promptVersion 一起贯穿 → system prompt 拼接时带版本号
# ============================================================

import re
import sqlite3
from datetime import datetime
from typing import Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

# ============================================================
# Constants
# ============================================================

FIRST_HOP_BUDGET_TOKENS = 3000    # 第一个 Agent 的历史 token 上限（保留兼容）
HANDOFF_BUDGET_TOKENS = 1500      # A2A 交接包的 token 上限
FACT_SECTION_BUDGET_RATIO = 0.4   # 事实段最多占 40% 预算
CONCLUSION_SECTION_BUDGET_RATIO = 0.5  # 结论段最多占 50% 预算
SHORT_MSG_THRESHOLD = 200          # 短消息阈值（字符数）

# ── 三阶段算法常量 ──
BURST_GAP_MINUTES = 15             # 静默缺口阈值（分钟）
BURST_MAX_MSGS = 12                # burst 最大消息数
BURST_MIN_MSGS = 4                 # burst 最小消息数
ANCHOR_TOP_N = 3                   # [DEPRECATED] v2 固定锚点数，v3 用 MIN_ANCHOR_SCORE + 预算自适应替代
MIN_ANCHOR_SCORE = 1               # v3: 锚点最低评分，低于此值不进 anchor 直接进 tombstone
LONG_MSG_CHARS = 200               # 长消息阈值（字符数，用于评分）
TOMBSTONE_TOKEN_RESERVE = 50       # v3: 为墓碑消息预留的 token 空间

# ── Related notes injection ──
RELATED_NOTES_BUDGET = 600          # 相关笔记注入的 token 预算
RELATED_NOTES_COUNT = 5             # 最多注入几条相关笔记
RELATED_NOTE_PREVIEW_CHARS = 120    # 每条笔记内容预览的字符上限

# 重要性评分权重
SCORE_THREAD_OPENER = 5            # 线程首条（用户第一句话）
SCORE_CODE_BLOCK = 3               # 含代码块
SCORE_MENTION_OR_TOOL = 2          # 含 @mention 或工具调用
SCORE_LONG_MSG = 1                 # 消息 >200 字符

# ── 分层触发常量（CC 五层金字塔） ──
LARGE_TOOL_RESULT_CHARS = 2000     # L1: 工具结果超过此阈值触发大文件卸载（~800 tokens）
LARGE_TOOL_RESULT_PREVIEW = 500    # L1: 保留前 500 字符作为预览
BUDGET_ESCALATION_RATIO = 1.5      # 超过 budget * 1.5 才进入完整三阶段（L5 tombstone）

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
# Message Priority Classification (deprecated — replaced by burst + anchor)
# ============================================================

def _priority(msg: BaseMessage) -> str:
    """
    [DEPRECATED] v1 优先级判断。v2 使用 burst detection + importance scoring 替代。
    保留此函数以保证外部测试导入兼容。
    """
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
# Drop Summary (deprecated — replaced by _build_tombstone)
# ============================================================

def _build_drop_summary(dropped: list[BaseMessage]) -> Optional[str]:
    """
    [DEPRECATED] v1 丢弃摘要。v2 使用 _build_tombstone() 替代。
    保留此函数以保证外部测试导入兼容。
    """
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
# Phase 1: Burst Detection
# ============================================================

def _parse_timestamp(ts_str: str) -> Optional[datetime]:
    """解析 SQLite datetime 文本。无法解析时返回 None。"""
    if not ts_str:
        return None
    try:
        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _detect_burst(msgs: list[dict]) -> int:
    """
    从最新消息往回找第一个 >= BURST_GAP_MINUTES 分钟的静默缺口，
    返回 burst 的起始 index（inclusive）。

    Clamp 到 [BURST_MIN_MSGS, BURST_MAX_MSGS]。
    语义链保护：如果 burst 首条是 tool 消息，向前扩展一行包含紧邻的 assistant。
    """
    n = len(msgs)
    if n == 0:
        return 0

    # 从最新往回找静默缺口
    burst_start = n - 1
    gap_found = False
    for i in range(n - 1, 0, -1):
        curr_ts = _parse_timestamp(msgs[i].get("created_at", ""))
        prev_ts = _parse_timestamp(msgs[i - 1].get("created_at", ""))
        if curr_ts and prev_ts:
            gap_seconds = (curr_ts - prev_ts).total_seconds()
            if gap_seconds >= BURST_GAP_MINUTES * 60:
                burst_start = i
                gap_found = True
                break

    if not gap_found:
        # 无静默缺口 → 整个对话是一个 burst（然后由 MAX 夹紧）
        burst_start = 0

    # Clamp 消息数
    burst_size = n - burst_start
    if burst_size > BURST_MAX_MSGS:
        burst_start = n - BURST_MAX_MSGS
    elif burst_size < BURST_MIN_MSGS:
        burst_start = max(0, n - BURST_MIN_MSGS)

    # 语义链保护：burst 首条是 tool → 向前扩到对应 assistant
    if burst_start < n and msgs[burst_start]["role"] == "tool":
        burst_start = max(0, burst_start - 1)

    return burst_start


# ============================================================
# Phase 2: Importance Scoring & Anchor Selection
# ============================================================

def _importance_score(msg: dict, is_thread_opener: bool) -> int:
    """对单条消息做重要性评分。"""
    score = 0
    content = msg.get("content", "")

    if is_thread_opener:
        score += SCORE_THREAD_OPENER
    if "```" in content:
        score += SCORE_CODE_BLOCK
    if "@" in content or msg.get("role") == "tool":
        score += SCORE_MENTION_OR_TOOL
    if len(content) > LONG_MSG_CHARS:
        score += SCORE_LONG_MSG

    return score


def _select_anchors(
    omitted: list[dict],
    first_user_idx: int | None,
    max_tokens: int = 0,
) -> tuple[list[dict], list[dict]]:
    """
    从省略消息中自适应选取锚点（v3 升级）。

    改造点：
      - 不再固定 ANCHOR_TOP_N，改为预算驱动：按评分降序取，直到 token 预算用完
      - MIN_ANCHOR_SCORE 门槛：评分低于此值的消息不进 anchor，直接归入 tombstone
      - 意图密集时高分消息多，tombstone 关键词密度自然变高

    返回 (anchors, tombstone_candidates)。
      anchors: 选中的锚点消息（用于原文插入）
      tombstone_candidates: 未达标/预算不够的消息（用于生成墓碑摘要）
    """
    if not omitted:
        return [], []

    # 评分 + 排序
    scored: list[tuple[int, int, dict]] = []
    for i, msg in enumerate(omitted):
        is_opener = (first_user_idx is not None
                     and msg["original_idx"] == first_user_idx)
        s = _importance_score(msg, is_opener)
        scored.append((s, i, msg))

    # 分数降序，同分时 index 升序（保持原始顺序的稳定 tie-break）
    scored.sort(key=lambda x: (-x[0], x[1]))

    # 预算驱动选取：评分达标 + 在 token 预算内
    anchors: list[dict] = []
    anchors_tokens = 0

    for s, i, msg in scored:
        if s < MIN_ANCHOR_SCORE:
            break  # 后续分数更低，不再考虑
        msg_tokens = estimate_tokens(msg.get("content", ""))
        if max_tokens > 0 and anchors_tokens + msg_tokens > max_tokens:
            continue  # 装不下了，跳过（仍进 tombstone）
        anchors.append(msg)
        anchors_tokens += msg_tokens

    # 未选为 anchor 的消息 → tombstone
    anchor_set = set(id(m) for m in anchors)
    tombstone_candidates = [m for m in omitted if id(m) not in anchor_set]

    return anchors, tombstone_candidates


# ============================================================
# Phase 3: Tombstone
# ============================================================

def _build_tombstone(omitted: list[dict]) -> str:
    """
    为被省略且未选为 anchor 的消息生成墓碑摘要。
    格式：[省略 N 条消息。关键词: X, Y。如需详情可搜索笔记库]
    """
    if not omitted:
        return ""

    n = len(omitted)
    keywords: list[str] = []

    for msg in omitted:
        content = msg.get("content", "")
        if msg.get("role") == "user":
            kw = content[:20].strip()
            if kw:
                keywords.append(kw)
        elif msg.get("role") == "tool":
            keywords.append("[工具调用]")

    # 去重，取前 5
    seen: set[str] = set()
    unique_kw: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_kw.append(kw)
    unique_kw = unique_kw[:5]

    kw_str = "、".join(unique_kw) if unique_kw else "对话"
    return f"[省略 {n} 条消息。关键词: {kw_str}。如需详情可搜索笔记库]"


# ============================================================
# Message Conversion
# ============================================================

def _msg_from_dict(m: dict) -> BaseMessage:
    """将 DB row dict 转换为 LangChain 消息对象。"""
    role = m["role"]
    content = m["content"]
    if role == "user":
        return HumanMessage(content=content)
    elif role == "assistant":
        return AIMessage(content=content)
    elif role == "tool":
        # tool 消息前缀标注，方便 Agent 理解
        return AIMessage(content=f"[工具结果] {content}")
    return AIMessage(content=content)


# ============================================================
# L1: Large File Offload（零成本，每次必做）
# ============================================================

def _offload_large_tool_results(msgs: list[dict]) -> list[dict]:
    """
    L1 大文件卸载：单条 tool 消息 > LARGE_TOOL_RESULT_CHARS 时，
    只留前 LARGE_TOOL_RESULT_PREVIEW 字符预览 + 取回提示。

    对应 CC L1 — 内容不丢，模型能通过 get_note 工具拿回完整结果。
    始终返回新 list，不改动输入。
    """
    result: list[dict] = []
    for msg in msgs:
        content = msg.get("content", "")
        if msg.get("role") == "tool" and isinstance(content, str) and len(content) > LARGE_TOOL_RESULT_CHARS:
            preview = content[:LARGE_TOOL_RESULT_PREVIEW]
            offloaded = {
                **msg,
                "content": (
                    f"{preview}\n\n"
                    f"[工具结果过长（原始 {len(content)} 字符），已截断。"
                    f"完整结果已存笔记库，可用 get_note 取回]"
                ),
            }
            result.append(offloaded)
        else:
            result.append(msg)
    return result


# ============================================================
# Related Notes Injection（Context 改造 — Phase 4）
# ============================================================

def _fetch_related_notes(conn: sqlite3.Connection, user_input: str) -> str:
    """
    根据用户当前输入搜索相关知识库笔记，格式化为上下文注入段。

    用 FTS5 关键词检索（同步，不依赖向量模型），
    匹配 title + content，返回一个 markdown 段供 Agent 参考。

    返回空字符串表示没有找到相关笔记。
    """
    if not user_input or not conn:
        return ""

    # FTS5 关键词检索
    escaped = '"' + user_input.replace('"', '""') + '"'
    try:
        rows = conn.execute(
            """
            SELECT n.title, n.content
            FROM notes_fts f
            JOIN notes n ON n.rowid = f.rowid
            WHERE notes_fts MATCH ?
              AND n.status = 'live'
              AND n.deleted_at IS NULL
            ORDER BY rank
            LIMIT ?
            """,
            (escaped, RELATED_NOTES_COUNT),
        ).fetchall()
    except Exception:
        return ""

    if not rows:
        return ""

    lines = ["## 相关知识库笔记"]
    for r in rows:
        title = r[0]
        content = r[1] or ""
        # 截断内容预览
        preview = content[:RELATED_NOTE_PREVIEW_CHARS].replace("\n", " ")
        if len(content) > RELATED_NOTE_PREVIEW_CHARS:
            preview += "…"
        lines.append(f"- **{title}**: {preview}")

    return "\n".join(lines)


# ============================================================
# First-Hop History Assembly (v2 — 三阶段算法)
# ============================================================

def assemble_context(
    conn: sqlite3.Connection,
    session_id: str,
    budget_tokens: int = FIRST_HOP_BUDGET_TOKENS,
    user_input: str | None = None,
) -> list[BaseMessage]:
    """
    从 DB 加载对话历史，按 CC 五层金字塔分层触发（v3）。

    每次强制 L1（大文件卸载，零成本），然后按总 token 量分三条路径：
      - 路径 A（total ≤ budget）：原样返回，零成本
      - 路径 B（total ≤ budget × 1.5）：只保留最近 burst，不摘要
      - 路径 C（total > budget × 1.5）：完整三阶段（burst + anchor + tombstone）

    Phase 1 — Burst Detection:
      从最新消息往回找 >=15 分钟静默缺口，保证最近一个对话 burst
      完整保留（最多 12 条，最少 4 条）。
      语义链保护：burst 首条若是 tool 消息，向前扩到对应 assistant。

    Phase 2 — Anchor Selection:
      对被省略的消息做重要性评分：
        +5 线程首条 / +3 含代码块 / +2 含 @mention 或工具调用 / +1 >200 字符
      选 top 3 作为锚点插入上下文。

    Phase 3 — Tombstone:
      对所有被省略的消息生成一条墓碑摘要：
      "[省略 N 条消息。关键词: X, Y。如需详情可搜索笔记库]"

    如果提供 user_input，还会搜索相关知识库笔记注入到上下文开头，
    让 Agent 无需显式调用 search_notes 就能感知已有知识。

    返回 LangChain 消息列表，按时间正序排列（不包含当前用户输入，由 router 追加）。
    """
    if not conn:
        return []

    rows = conn.execute(
        "SELECT role, content, created_at FROM messages "
        "WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()

    if not rows:
        return []

    # ── 构建消息元数据列表 ──
    all_msgs: list[dict] = []
    first_user_idx: int | None = None

    for idx, (role, content, created_at) in enumerate(rows):
        msg = {
            "role": role,
            "content": content,
            "created_at": created_at,
            "original_idx": idx,
        }
        all_msgs.append(msg)

        if first_user_idx is None and role == "user":
            first_user_idx = idx

    # ── L1: 大文件卸载（零成本，每次必做） ──
    all_msgs = _offload_large_tool_results(all_msgs)

    # ── 触发阈值：能不压就不压（CC 精髓） ──
    total_tokens = sum(estimate_tokens(m["content"]) for m in all_msgs)

    # 三条路径都收集到 result，最后统一注入 related notes
    result: list[BaseMessage] = []

    if total_tokens <= budget_tokens:
        # 路径 A：不压，零成本原样返回
        result = [_msg_from_dict(m) for m in all_msgs]

    elif total_tokens <= int(budget_tokens * BUDGET_ESCALATION_RATIO):
        # 路径 B：轻量清理 — 只保留最近 burst，不选 anchor，不生成 tombstone
        burst_start = _detect_burst(all_msgs)
        result = [_msg_from_dict(m) for m in all_msgs[burst_start:]]

    else:
        # ── 路径 C：超标严重，走完整三阶段（L5 tombstone） ──
        burst_start = _detect_burst(all_msgs)
        burst_msgs = all_msgs[burst_start:]
        omitted_msgs = all_msgs[:burst_start]

        # Phase 2: Anchor Selection（v3 预算自适应）
        burst_tokens = sum(estimate_tokens(m["content"]) for m in burst_msgs)
        anchor_budget = max(0, budget_tokens - burst_tokens - TOMBSTONE_TOKEN_RESERVE)
        anchors, tombstone_msgs = _select_anchors(omitted_msgs, first_user_idx, anchor_budget)

        # Phase 3: Tombstone
        tombstone = _build_tombstone(tombstone_msgs)

        if tombstone:
            result.append(HumanMessage(content=tombstone))

        # Anchors 按原始 index 排序
        anchors.sort(key=lambda m: m["original_idx"])
        for m in anchors:
            result.append(_msg_from_dict(m))

        # Burst 已经按时间正序（来自 DB ORDER BY created_at ASC）
        for m in burst_msgs:
            result.append(_msg_from_dict(m))

    # ── Related notes injection（Context 改造 — Phase 4） ──
    # 在所有路径的结果开头注入相关笔记，让 Agent 无需显式调用
    # search_notes 就能感知已有知识。
    if user_input:
        related_section = _fetch_related_notes(conn, user_input)
        if related_section:
            result.insert(0, HumanMessage(content=related_section))

    return result


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
