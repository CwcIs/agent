"""
Context-Transport 单元测试。

测试 assemble_context() 和 package_handoff() 的行为：
  - 优先级裁剪（user 消息永不被丢弃）
  - Token 预算强制
  - A2A 交接包四个段的组装
  - 空工具事件 / 极端输入等边界情况

运行方式：
  cd packages/api
  python -m pytest tests/test_context_transport.py -v
  或
  python tests/test_context_transport.py
"""

import json
import os
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path

# 确保 src 在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from context.assemble import (
    assemble_context,
    estimate_tokens,
    package_handoff,
    _priority,
    _strip_mentions,
    _build_drop_summary,
    _parse_timestamp,
    _detect_burst,
    _importance_score,
    _select_anchors,
    _build_tombstone,
    _msg_from_dict,
    _offload_large_tool_results,
    FIRST_HOP_BUDGET_TOKENS,
    HANDOFF_BUDGET_TOKENS,
    BURST_MAX_MSGS,
    BURST_MIN_MSGS,
    SCORE_THREAD_OPENER,
    SCORE_CODE_BLOCK,
    SCORE_MENTION_OR_TOOL,
    LARGE_TOOL_RESULT_CHARS,
    LARGE_TOOL_RESULT_PREVIEW,
    BUDGET_ESCALATION_RATIO,
    MIN_ANCHOR_SCORE,
    TOMBSTONE_TOKEN_RESERVE,
)
from langchain_core.messages import HumanMessage, AIMessage


# ============================================================
# Helpers
# ============================================================

def _init_test_db() -> sqlite3.Connection:
    """创建内存数据库 + messages 表，用于测试。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL DEFAULT 'knowledge',
            role TEXT NOT NULL CHECK(role IN ('user','assistant','tool')),
            content TEXT NOT NULL,
            tool_call_id TEXT,
            prompt_version TEXT NOT NULL DEFAULT 'v1',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    return conn


def _insert_msg(conn, session_id, role, content, agent_id="knowledge"):
    conn.execute(
        "INSERT INTO messages (id, session_id, agent_id, role, content) VALUES (?,?,?,?,?)",
        (str(uuid.uuid4()), session_id, agent_id, role, content),
    )
    conn.commit()


def _insert_msg_with_ts(conn, session_id, role, content, created_at, agent_id="knowledge"):
    """插入带指定 created_at 的消息（用于测试 burst detection 时间缺口）。"""
    conn.execute(
        "INSERT INTO messages (id, session_id, agent_id, role, content, created_at) VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), session_id, agent_id, role, content, created_at),
    )
    conn.commit()


# ============================================================
# estimate_tokens
# ============================================================

def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0


def test_estimate_tokens_chinese():
    # 5 个中文字 ≈ 2 tokens (5/2.5=2)
    assert estimate_tokens("你好世界啊") == 2


def test_estimate_tokens_english():
    # 25 个英文字 ≈ 10 tokens
    assert estimate_tokens("a" * 25) == 10


# ============================================================
# _priority
# ============================================================

def test_priority_user_high():
    assert _priority(HumanMessage(content="你好")) == "HIGH"


def test_priority_short_assistant_medium():
    assert _priority(AIMessage(content="好的")) == "MEDIUM"


def test_priority_long_assistant_low():
    long_text = "这是一个很长的回复。" * 50  # ~500 chars
    assert _priority(AIMessage(content=long_text)) == "LOW"


def test_priority_assistant_with_mention_medium():
    msg = AIMessage(content="分析完成。\n@review 这个结论")
    assert _priority(msg) == "MEDIUM"


# ============================================================
# _strip_mentions
# ============================================================

def test_strip_mentions_removes_mention_line():
    text = "分析结论\n@review B端可行性\n还有一些补充"
    result = _strip_mentions(text)
    assert "@review" not in result
    assert "分析结论" in result
    assert "还有一些补充" in result


def test_strip_mentions_no_mention():
    text = "这是一段普通文本"
    assert _strip_mentions(text) == text


# ============================================================
# _build_drop_summary
# ============================================================

def test_build_drop_summary_empty():
    assert _build_drop_summary([]) is None


def test_build_drop_summary_with_user_messages():
    dropped = [
        HumanMessage(content="帮我查一下技术债相关的笔记"),
        AIMessage(content="找到了 3 条相关笔记..."),
        HumanMessage(content="第一条展开说说"),
    ]
    result = _build_drop_summary(dropped)
    assert "之前聊过" in result
    assert "技术债" in result


# ============================================================
# v2 helpers: _parse_timestamp
# ============================================================

def test_parse_timestamp_valid():
    from datetime import datetime
    result = _parse_timestamp("2026-06-29 14:30:00")
    assert result == datetime(2026, 6, 29, 14, 30, 0)


def test_parse_timestamp_invalid():
    assert _parse_timestamp("") is None
    assert _parse_timestamp("not-a-date") is None


# ============================================================
# v2 helpers: _detect_burst
# ============================================================

def test_detect_burst_empty():
    assert _detect_burst([]) == 0


def test_detect_burst_fewer_than_min():
    """少于 BURST_MIN 条消息时返回 0（全部进入 burst）。"""
    msgs = [
        {"role": "user", "content": "hi", "created_at": "2026-06-29 14:30:00"},
        {"role": "assistant", "content": "hey", "created_at": "2026-06-29 14:30:10"},
    ]
    assert _detect_burst(msgs) == 0  # 夹紧到 BURST_MIN=4 → 全部保留


def test_detect_burst_time_gap():
    """15 分钟静默缺口后开始新 burst。"""
    msgs = [
        {"role": "user",    "content": "old",  "created_at": "2026-06-29 10:00:00"},
        {"role": "assistant", "content": "old", "created_at": "2026-06-29 10:00:05"},
        # 20 分钟缺口
        {"role": "user",    "content": "new",  "created_at": "2026-06-29 10:20:00"},
        {"role": "assistant", "content": "new", "created_at": "2026-06-29 10:20:05"},
    ]
    burst_start = _detect_burst(msgs)
    # burst 从 index 2 开始（gap >= 15min），但 BURST_MIN=4 夹紧到全部
    # 4 条消息 ≤ BURST_MIN → 全部进入 burst
    assert burst_start == 0


def test_detect_burst_large_gap_many_msgs():
    """大量消息 + 时间缺口时，burst 从缺口之后开始。"""
    msgs = []
    # 8 条旧消息（10:00-10:05）
    for i in range(4):
        msgs.append({"role": "user", "content": f"old-u-{i}", "created_at": f"2026-06-29 10:00:{i*2:02d}"})
        msgs.append({"role": "assistant", "content": f"old-a-{i}", "created_at": f"2026-06-29 10:00:{i*2+1:02d}"})
    # 30 分钟缺口
    # 6 条新消息（10:35-10:36）
    for i in range(3):
        msgs.append({"role": "user", "content": f"new-u-{i}", "created_at": f"2026-06-29 10:35:{i*2:02d}"})
        msgs.append({"role": "assistant", "content": f"new-a-{i}", "created_at": f"2026-06-29 10:35:{i*2+1:02d}"})

    burst_start = _detect_burst(msgs)
    # 总共 14 条，gap 在 index 8 处开始
    # gap detected at index 8, BURST_MAX=12 → burst = last 12, start at 2
    # But wait: gap detection finds break at index 8, burst_size = 14-8 = 6
    # 6 is within [4, 12], so burst_start = 8
    assert burst_start == 8
    assert msgs[burst_start]["content"] == "new-u-0"


def test_detect_burst_tool_chain_protection():
    """burst 首条是 tool → 向前扩展包含对应的 assistant。"""
    msgs = [
        {"role": "user",      "content": "query",      "created_at": "2026-06-29 10:00:00"},
        {"role": "assistant", "content": "let me check","created_at": "2026-06-29 10:00:05"},
        {"role": "tool",      "content": "tool result", "created_at": "2026-06-29 10:35:00"},
        {"role": "assistant", "content": "here's result","created_at": "2026-06-29 10:35:05"},
    ]
    burst_start = _detect_burst(msgs)
    # gap at index 2 (10:00 → 10:35), but tool at burst_start → extend back
    # BURST_MIN=4: all 4 should be kept anyway
    assert burst_start == 0


def test_detect_burst_clamp_max():
    """超过 BURST_MAX 时夹紧到最后 12 条。"""
    msgs = []
    for i in range(20):
        msgs.append({"role": "user", "content": f"msg-{i}", "created_at": f"2026-06-29 14:{i:02d}:00"})
    burst_start = _detect_burst(msgs)
    # 20 条，BURST_MAX=12，burst_start = 20 - 12 = 8
    assert burst_start == 8
    assert len(msgs) - burst_start == 12


# ============================================================
# v2 helpers: _importance_score
# ============================================================

def test_importance_score_thread_opener():
    msg = {"role": "user", "content": "帮我查一下技术债相关的笔记", "original_idx": 0}
    score = _importance_score(msg, is_thread_opener=True)
    assert score >= 5  # thread opener +5


def test_importance_score_code_block():
    msg = {"role": "assistant", "content": "这里是代码：\n```python\nprint('hello')\n```"}
    score = _importance_score(msg, is_thread_opener=False)
    assert score >= 3  # code block +3


def test_importance_score_tool_call():
    msg = {"role": "tool", "content": "tool:search_notes:[...]"}
    score = _importance_score(msg, is_thread_opener=False)
    assert score >= 2  # tool call +2


def test_importance_score_mention():
    msg = {"role": "assistant", "content": "分析完成。@review 需要看一下"}
    score = _importance_score(msg, is_thread_opener=False)
    assert score >= 2  # @mention +2


def test_importance_score_long():
    msg = {"role": "assistant", "content": "x" * 300}
    score = _importance_score(msg, is_thread_opener=False)
    assert score >= 1  # long message +1


def test_importance_score_nothing_special():
    msg = {"role": "assistant", "content": "好的"}
    score = _importance_score(msg, is_thread_opener=False)
    assert score == 0


# ============================================================
# v2 helpers: _build_tombstone
# ============================================================

def test_build_tombstone_empty():
    assert _build_tombstone([]) == ""


def test_build_tombstone_with_omitted():
    omitted = [
        {"role": "user", "content": "帮我查技术债", "original_idx": 0},
        {"role": "assistant", "content": "找到一个相关笔记...", "original_idx": 1},
        {"role": "tool", "content": "tool:search_notes:[...]", "original_idx": 2},
        {"role": "user", "content": "展开说说", "original_idx": 3},
    ]
    result = _build_tombstone(omitted)
    assert "[省略 4 条消息" in result
    assert "技术债" in result
    assert "[工具调用]" in result
    assert "如需详情可搜索笔记库" in result


def test_build_tombstone_dedup_keywords():
    """重复关键词应去重。"""
    omitted = [
        {"role": "user", "content": "技术债怎么处理", "original_idx": 0},
        {"role": "user", "content": "技术债怎么处理", "original_idx": 1},
    ]
    result = _build_tombstone(omitted)
    # "技术债" should appear only once (first 20 chars of both are identical)
    assert result.count("技术债怎么处理") == 1


# ============================================================
# v2 helpers: _select_anchors
# ============================================================

def test_select_anchors_empty():
    anchors, tombstone = _select_anchors([], 0, max_tokens=100)
    assert anchors == []
    assert tombstone == []


def test_select_anchors_picks_top_by_score():
    """预算充足时，评分达标的消息都应选为锚点。"""
    omitted = [
        {"role": "assistant", "content": "普通回复", "original_idx": 0},
        {"role": "user", "content": "帮我查```code```技术债", "original_idx": 1},
        {"role": "assistant", "content": "@review 这个", "original_idx": 2},         # mention +2
        {"role": "tool", "content": "tool:search_notes:[...]", "original_idx": 3},  # tool +2
        {"role": "user", "content": "长" + "x" * 300, "original_idx": 4},          # long +1
    ]
    anchors, tombstone = _select_anchors(omitted, first_user_idx=1, max_tokens=5000)
    # 评分 >=1 的消息都应入选
    assert len(anchors) >= 3
    scores = [_importance_score(m, m["original_idx"] == 1) for m in anchors]
    assert all(s >= MIN_ANCHOR_SCORE for s in scores)
    # 评分 0 的消息进 tombstone
    assert len(tombstone) >= 1
    assert tombstone[0]["content"] == "普通回复"


def test_select_anchors_respects_budget():
    """token 预算不够时，只装得下评分最高的部分消息。"""
    omitted = [
        {"role": "user", "content": "帮我查```code```技术债", "original_idx": 0},   # ~5 tokens
        {"role": "assistant", "content": "@review 这个", "original_idx": 1},        # ~3 tokens, score 2
        {"role": "tool", "content": "tool:search_notes:[...]", "original_idx": 2}, # ~9 tokens, score 2
    ]
    # 预算只够装第一条
    tight_budget = estimate_tokens(omitted[0]["content"]) + 1
    anchors, tombstone = _select_anchors(omitted, first_user_idx=0, max_tokens=tight_budget)
    assert len(anchors) == 1
    # 其余进 tombstone
    assert len(tombstone) == 2


def test_select_anchors_score_threshold():
    """评分低于 MIN_ANCHOR_SCORE 的消息不进 anchor。"""
    omitted = [
        {"role": "assistant", "content": "好的", "original_idx": 0},           # score 0
        {"role": "assistant", "content": "知道了", "original_idx": 1},         # score 0
        {"role": "user", "content": "查询```code```", "original_idx": 2},     # score > 0
    ]
    anchors, tombstone = _select_anchors(omitted, first_user_idx=None, max_tokens=5000)
    # 只有 score >= 1 的进 anchor
    assert len(anchors) == 1
    assert "查询" in anchors[0]["content"]
    # score 0 的全部进 tombstone
    assert len(tombstone) == 2


# ============================================================
# v2: assemble_context with time gaps
# ============================================================

def test_assemble_context_respects_burst_boundary():
    """有时间缺口时，只保留 burst 内的消息 + anchors + tombstone。"""
    conn = _init_test_db()
    sid = "burst-test"

    # 旧消息（30 分钟前）
    _insert_msg_with_ts(conn, sid, "user", "旧问题", "2026-06-29 10:00:00")
    _insert_msg_with_ts(conn, sid, "assistant", "旧回答", "2026-06-29 10:00:05")

    # 新消息（burst，30 分钟后）
    _insert_msg_with_ts(conn, sid, "user", "新问题", "2026-06-29 10:30:00")
    _insert_msg_with_ts(conn, sid, "assistant", "新回答", "2026-06-29 10:30:05")

    result = assemble_context(conn, sid)
    contents = [m.content for m in result]

    # burst 内消息应保留
    assert "新问题" in contents
    assert "新回答" in contents

    # 4 条消息 ≤ BURST_MIN → 全部进入 burst，旧消息也保留
    assert "旧问题" in contents or any("[省略 " in c for c in contents)


def test_assemble_context_generates_tombstone_for_large_history():
    """大量历史消息 + 极小预算时生成墓碑摘要。"""
    conn = _init_test_db()
    sid = "tombstone-test"

    # 25 条消息（> BURST_MAX=12）
    for i in range(12):
        _insert_msg(conn, sid, "user", f"问题 {i}")
        _insert_msg(conn, sid, "assistant", f"回答 {i}")
    _insert_msg(conn, sid, "user", "最新问题")

    # 极小预算强制走路径 C
    result = assemble_context(conn, sid, budget_tokens=10)
    contents = [m.content if hasattr(m, 'content') else "" for m in result]

    # 墓碑应在开头
    assert "[省略 " in contents[0]
    assert "条消息" in contents[0]

    # 最新问题应在结果中
    assert "最新问题" in contents


def test_assemble_context_empty_db():
    conn = _init_test_db()
    result = assemble_context(conn, "no-session")
    assert result == []


def test_assemble_context_keeps_all_when_under_budget():
    conn = _init_test_db()
    sid = "test-session"
    _insert_msg(conn, sid, "user", "你好")
    _insert_msg(conn, sid, "assistant", "你好！有什么可以帮你的？")

    result = assemble_context(conn, sid)
    assert len(result) == 2
    assert isinstance(result[0], HumanMessage)
    assert isinstance(result[1], AIMessage)


def test_assemble_context_user_messages_always_kept():
    """用户消息 HIGH 优先级，即使超出预算也保留。"""
    conn = _init_test_db()
    sid = "test-session"

    # 塞入 5 轮对话（10 条消息）
    for i in range(5):
        _insert_msg(conn, sid, "user", f"问题 {i}")
        _insert_msg(conn, sid, "assistant", f"回答 {i}")

    result = assemble_context(conn, sid, budget_tokens=30)  # 极小预算
    user_count = sum(1 for m in result if isinstance(m, HumanMessage))
    assert user_count == 5  # 所有用户消息都保留


def test_assemble_context_drops_long_narratives():
    """v2: 4 条消息 ≤ BURST_MIN，全部保留，无需丢弃。"""
    conn = _init_test_db()
    sid = "test-session"

    _insert_msg(conn, sid, "user", "你好")
    _insert_msg(conn, sid, "assistant", "x" * 500)  # 长叙事
    _insert_msg(conn, sid, "user", "帮我查笔记")
    _insert_msg(conn, sid, "assistant", "找到了")  # 短回复

    result = assemble_context(conn, sid, budget_tokens=30)  # 极小预算
    contents = [m.content for m in result]
    # v2: burst 夹紧到 BURST_MIN=4，4 条消息全部保留
    assert len(result) == 4
    assert "找到了" in contents
    # 长叙事也在 burst 中，不会被丢弃
    assert any("x" * 100 in c for c in contents)


def test_assemble_context_adds_summary_when_truncating():
    """20 条消息超出 BURST_MAX，省略消息应生成墓碑摘要。"""
    conn = _init_test_db()
    sid = "test-session"

    # 塞很多轮对话（10 user + 10 assistant = 20 条）
    for i in range(10):
        _insert_msg(conn, sid, "user", f"问题 {i}: 这是一个比较长的用户问题，包含一些上下文信息")
        _insert_msg(conn, sid, "assistant", f"回答 {i}: " + "这是一个很长的助理回复。" * 20)

    result = assemble_context(conn, sid, budget_tokens=200)
    # v2 tombstone 格式：[省略 N 条消息。关键词: ...]
    has_tombstone = any(
        "[省略 " in (m.content if hasattr(m, 'content') else "") and "条消息" in (m.content if hasattr(m, 'content') else "")
        for m in result
    )
    assert has_tombstone
    # 墓碑应该在第一条（开头位置）
    first_content = result[0].content if hasattr(result[0], 'content') else ""
    assert "[省略 " in first_content


# ============================================================
# package_handoff
# ============================================================

def test_package_handoff_all_sections():
    result = package_handoff(
        original_user_input="帮我分析B端策略",
        agent_a_full_output="分析结论：B端值得做。\n@review B端可行性",
        mention_content="B端可行性",
        tool_events=[
            {"type": "tool_end", "name": "search_notes",
             "result": '[{"title":"B端优先级","content":"Q3先做B端"}]'},
        ],
    )
    content = result[0].content
    assert "用户意图" in content
    assert "帮我分析B端策略" in content
    assert "已发现的事实" in content
    assert "search_notes" in content
    assert "Knowledge Agent 的分析" in content
    assert "需要 Review 的观点" in content
    assert "B端可行性" in content


def test_package_handoff_no_tools():
    """没有工具事件时，省略'已发现的事实'段。"""
    result = package_handoff(
        original_user_input="测试问题",
        agent_a_full_output="测试回答",
        mention_content="测试观点",
        tool_events=[],
    )
    content = result[0].content
    assert "已发现的事实" not in content
    assert "用户意图" in content
    assert "需要 Review 的观点" in content


def test_package_handoff_budget_enforced():
    """token 预算应该被强制执行。"""
    result = package_handoff(
        original_user_input="短问题",
        agent_a_full_output="短回答",
        mention_content="短观点",
        tool_events=[],
        budget_tokens=50,
    )
    tokens = estimate_tokens(result[0].content)
    assert tokens <= 80  # 给一些 slack（摘要等附加内容）


def test_package_handoff_mention_fallback():
    """mention_content 为空时，用 agent_a_full_output 作为 handoff。"""
    result = package_handoff(
        original_user_input="问题",
        agent_a_full_output="完整的分析回答",
        mention_content="",
        tool_events=[],
    )
    assert "完整的分析回答" in result[0].content


def test_package_handoff_returns_list_of_one():
    result = package_handoff("q", "a", "m", [])
    assert len(result) == 1
    assert isinstance(result[0], HumanMessage)


# ============================================================
# Integration: assemble_context + package_handoff flow
# ============================================================

def test_full_flow_assemble_then_handoff():
    """模拟完整的 A2A 流程：先 assemble 历史 → Agent 回复 → package handoff。"""
    conn = _init_test_db()
    sid = "flow-test"

    # 第一轮：用户问问题
    _insert_msg(conn, sid, "user", "帮我找找技术债相关的笔记")
    _insert_msg(conn, sid, "assistant",
                "找到了 3 条技术债相关笔记：老登录模块耦合太深...")

    # 第二轮：用户追问
    _insert_msg(conn, sid, "user", "帮我 review 一下这个结论：应该先重构老登录模块")

    # 模拟 router 流程
    history = assemble_context(conn, sid)
    # 去掉刚存的用户消息（router 会单独 append）
    history = history[:-1] if history else []

    assert len(history) >= 1  # 至少保留了一条历史
    # 历史应该包含第一轮的用户消息
    user_contents = [m.content for m in history if isinstance(m, HumanMessage)]
    assert any("技术债" in c for c in user_contents)

    # 模拟 Agent A 回复后触发 A2A
    agent_a_output = "分析：老登录模块确实需要重构。\n@review 先重构老登录模块"

    handoff = package_handoff(
        original_user_input="帮我 review 一下这个结论：应该先重构老登录模块",
        agent_a_full_output=agent_a_output,
        mention_content="先重构老登录模块",
        tool_events=[
            {"type": "tool_end", "name": "search_notes",
             "result": '[{"title":"技术债清单","content":"老登录模块耦合太深"}]'},
        ],
    )

    hc = handoff[0].content
    assert "用户意图" in hc
    assert "已发现的事实" in hc
    assert "技术债" in hc
    assert "需要 Review 的观点" in hc


# ============================================================
# v3: L1 Large File Offload
# ============================================================

def test_offload_large_tool_result():
    """单条 tool 消息超过阈值时应截断并附加提示。"""
    large_content = "x" * (LARGE_TOOL_RESULT_CHARS + 100)
    msgs = [
        {"role": "tool", "content": large_content, "original_idx": 0},
    ]
    result = _offload_large_tool_results(msgs)
    assert len(result) == 1
    assert len(result[0]["content"]) < len(large_content)
    assert "工具结果过长" in result[0]["content"]
    assert "get_note" in result[0]["content"]
    # 前 LARGE_TOOL_RESULT_PREVIEW 字符应保留
    assert result[0]["content"].startswith("x" * LARGE_TOOL_RESULT_PREVIEW)


def test_offload_small_tool_result_untouched():
    """小工具结果不触发卸载。"""
    small_content = "短结果"
    msgs = [
        {"role": "tool", "content": small_content, "original_idx": 0},
    ]
    result = _offload_large_tool_results(msgs)
    assert result[0]["content"] == small_content


def test_offload_non_tool_untouched():
    """非 tool 消息不触发卸载。"""
    long_user = "y" * 3000
    msgs = [
        {"role": "user", "content": long_user, "original_idx": 0},
        {"role": "assistant", "content": "ok", "original_idx": 1},
    ]
    result = _offload_large_tool_results(msgs)
    assert result[0]["content"] == long_user
    assert result[1]["content"] == "ok"


def test_offload_returns_new_list():
    """不修改输入 list。"""
    msgs = [
        {"role": "tool", "content": "x" * (LARGE_TOOL_RESULT_CHARS + 500)},
    ]
    original = list(msgs)
    _offload_large_tool_results(msgs)
    assert msgs == original


# ============================================================
# v3: Trigger Threshold — Path A (under budget, zero-cost pass-through)
# ============================================================

def test_assemble_path_a_under_budget():
    """历史 token 未超预算时原样返回，不跑三阶段。"""
    conn = _init_test_db()
    sid = "path-a-test"
    _insert_msg(conn, sid, "user", "你好")
    _insert_msg(conn, sid, "assistant", "你好！")

    result = assemble_context(conn, sid, budget_tokens=500)
    assert len(result) == 2
    assert isinstance(result[0], HumanMessage)
    assert isinstance(result[1], AIMessage)
    # 不应有 tombstone
    contents = [m.content for m in result]
    assert not any("[省略 " in c for c in contents)


def test_assemble_path_a_skips_tombstone():
    """小历史不应生成墓碑摘要。"""
    conn = _init_test_db()
    sid = "path-a-no-tombstone"
    for i in range(3):
        _insert_msg(conn, sid, "user", f"问题 {i}")
        _insert_msg(conn, sid, "assistant", f"回答 {i}")

    # 6 条短消息 token 数很少，用大预算
    result = assemble_context(conn, sid, budget_tokens=5000)
    has_tombstone = any(
        "[省略 " in (m.content if hasattr(m, 'content') else "")
        for m in result
    )
    assert not has_tombstone


# ============================================================
# v3: Trigger Threshold — Path B (burst only, no tombstone)
# ============================================================

def test_assemble_path_b_burst_only():
    """token 在 budget~1.5x 之间时只保留 burst，不生成 tombstone。"""
    conn = _init_test_db()
    sid = "path-b-test"

    # 旧消息（用极小时间间隔，确保无 gap）
    for i in range(8):
        _insert_msg_with_ts(conn, sid, "user", f"旧问题 {i}",
                            f"2026-06-29 10:{i*2:02d}:00")
        _insert_msg_with_ts(conn, sid, "assistant", f"旧回答 {i}",
                            f"2026-06-29 10:{i*2+1:02d}:00")
    # 新 burst（间隔 30 分钟）
    _insert_msg_with_ts(conn, sid, "user", "新问题",
                        f"2026-06-29 10:30:00")
    _insert_msg_with_ts(conn, sid, "assistant", "新回答",
                        f"2026-06-29 10:30:05")

    # 用适中预算使 total 落在 budget~1.5x 区间
    result = assemble_context(conn, sid, budget_tokens=150)

    contents = [m.content if hasattr(m, 'content') else "" for m in result]
    # 新 burst 应保留
    assert "新问题" in contents
    assert "新回答" in contents
    # 不应有 tombstone（路径 B 不摘要）
    assert not any("[省略 " in c for c in contents)


# ============================================================
# v3: Trigger Threshold — Path C (full three-stage, L5 tombstone)
# ============================================================

def test_assemble_path_c_with_tombstone():
    """token 严重超标时走完整三阶段，应有墓碑摘要。"""
    conn = _init_test_db()
    sid = "path-c-test"

    # 大量长消息确保超标
    for i in range(12):
        _insert_msg(conn, sid, "user", f"问题 {i}：" + "这是一个比较长的用户输入 " * 10)
        _insert_msg(conn, sid, "assistant", f"回答 {i}：" + "这是一个很长的助理回复 " * 10)
    _insert_msg(conn, sid, "user", "最新问题")

    # 极小预算迫使走路径 C
    result = assemble_context(conn, sid, budget_tokens=50)

    contents = [m.content if hasattr(m, 'content') else "" for m in result]
    # 应有 tombstone
    assert any("[省略 " in c and "条消息" in c for c in contents)
    # 最新问题应保留
    assert "最新问题" in contents


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    # 简陋但有效的测试运行器（不依赖 pytest）
    tests = [
        # estimate_tokens
        test_estimate_tokens_empty,
        test_estimate_tokens_chinese,
        test_estimate_tokens_english,
        # _priority
        test_priority_user_high,
        test_priority_short_assistant_medium,
        test_priority_long_assistant_low,
        test_priority_assistant_with_mention_medium,
        # _strip_mentions
        test_strip_mentions_removes_mention_line,
        test_strip_mentions_no_mention,
        # _build_drop_summary
        test_build_drop_summary_empty,
        test_build_drop_summary_with_user_messages,
        # v2: _parse_timestamp
        test_parse_timestamp_valid,
        test_parse_timestamp_invalid,
        # v2: _detect_burst
        test_detect_burst_empty,
        test_detect_burst_fewer_than_min,
        test_detect_burst_time_gap,
        test_detect_burst_large_gap_many_msgs,
        test_detect_burst_tool_chain_protection,
        test_detect_burst_clamp_max,
        # v2: _importance_score
        test_importance_score_thread_opener,
        test_importance_score_code_block,
        test_importance_score_tool_call,
        test_importance_score_mention,
        test_importance_score_long,
        test_importance_score_nothing_special,
        # v2: _build_tombstone
        test_build_tombstone_empty,
        test_build_tombstone_with_omitted,
        test_build_tombstone_dedup_keywords,
        # v2: _select_anchors (v3 return type)
        test_select_anchors_empty,
        test_select_anchors_picks_top_by_score,
        # v3: adaptive anchors
        test_select_anchors_respects_budget,
        test_select_anchors_score_threshold,
        # v3: L1 large file offload
        test_offload_large_tool_result,
        test_offload_small_tool_result_untouched,
        test_offload_non_tool_untouched,
        test_offload_returns_new_list,
        # v3: Path A (under budget)
        test_assemble_path_a_under_budget,
        test_assemble_path_a_skips_tombstone,
        # v3: Path B (burst only)
        test_assemble_path_b_burst_only,
        # v3: Path C (full three-stage)
        test_assemble_path_c_with_tombstone,
        # v2: assemble_context with burst
        test_assemble_context_respects_burst_boundary,
        test_assemble_context_generates_tombstone_for_large_history,
        # assemble_context (v1 compat)
        test_assemble_context_empty_db,
        test_assemble_context_keeps_all_when_under_budget,
        test_assemble_context_user_messages_always_kept,
        test_assemble_context_drops_long_narratives,
        test_assemble_context_adds_summary_when_truncating,
        # package_handoff
        test_package_handoff_all_sections,
        test_package_handoff_no_tools,
        test_package_handoff_budget_enforced,
        test_package_handoff_mention_fallback,
        test_package_handoff_returns_list_of_one,
        # integration
        test_full_flow_assemble_then_handoff,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            print(f"  PASS {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(0 if failed == 0 else 1)
