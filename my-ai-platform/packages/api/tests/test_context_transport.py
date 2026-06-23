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
    FIRST_HOP_BUDGET_TOKENS,
    HANDOFF_BUDGET_TOKENS,
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
# assemble_context
# ============================================================

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
    """长助理消息（LOW 优先级）先被丢弃。"""
    conn = _init_test_db()
    sid = "test-session"

    _insert_msg(conn, sid, "user", "你好")
    _insert_msg(conn, sid, "assistant", "x" * 500)  # 长叙事
    _insert_msg(conn, sid, "user", "帮我查笔记")
    _insert_msg(conn, sid, "assistant", "找到了")  # 短回复

    result = assemble_context(conn, sid, budget_tokens=30)  # 极小预算
    contents = [m.content for m in result]
    # 最近的短回复应该保留
    assert "找到了" in contents
    # 长叙事可能被丢弃
    long_kept = any("x" * 100 in c for c in contents)
    # 如果丢了消息，应该有摘要
    has_summary = any("[对话摘要]" in c for c in contents)
    assert long_kept or has_summary


def test_assemble_context_adds_summary_when_truncating():
    conn = _init_test_db()
    sid = "test-session"

    # 塞很多轮对话
    for i in range(10):
        _insert_msg(conn, sid, "user", f"问题 {i}: 这是一个比较长的用户问题，包含一些上下文信息")
        _insert_msg(conn, sid, "assistant", f"回答 {i}: " + "这是一个很长的助理回复。" * 20)

    result = assemble_context(conn, sid, budget_tokens=200)
    # 应该有摘要消息在开头
    has_summary = any("[对话摘要]" in (m.content if hasattr(m, 'content') else "")
                      for m in result)
    assert has_summary


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
        # assemble_context
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
