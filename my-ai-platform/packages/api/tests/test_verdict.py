"""
Verdict-Detect 单元测试。

测试 detect_verdict() 的行为：
  - natural_end — 文本像最终答复，自然终止
  - missing_handoff — 无 @mention 且不像最终答复
  - loop_detected — 同一对 Agent 来回转手
  - max_depth — 深度超限硬终止
  - depth_warning — 接近上限但未超

运行方式：
  cd packages/api
  python tests/test_verdict.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.verdict import (
    detect_verdict,
    _is_likely_final,
    _is_vague,
    _extract_keywords,
    _HandoffRecord,
)


# ============================================================
# _is_likely_final
# ============================================================

def test_is_likely_final_with_closing():
    assert _is_likely_final("综上所述，B端策略建议是优先做SaaS。") is True
    assert _is_likely_final("以上就是关于技术债的分析。希望对你有帮助") is True
    assert _is_likely_final("最后，总结一下：先重构登录模块。") is True
    assert _is_likely_final("In summary, the B2B approach is better.") is True
    assert _is_likely_final("I hope this helps clarify things.") is True


def test_is_likely_final_without_closing():
    assert _is_likely_final("从搜索结果看，你之前记过3条相关笔记。") is False
    assert _is_likely_final("") is False


# ============================================================
# _is_vague
# ============================================================

def test_is_vague_short_text():
    assert _is_vague("我") is True
    assert _is_vague("好的") is True


def test_is_vague_uncertain_phrase():
    assert _is_vague("我再想想这个问题") is True
    assert _is_vague("让我确认一下再回复你") is True
    assert _is_vague("稍等，让我查一下") is True


def test_is_vague_long_clear_text():
    long_text = "根据你的笔记库，你有三条关于技术债的记录。第一条是关于..." * 3
    assert _is_vague(long_text) is False


# ============================================================
# _extract_keywords
# ============================================================

def test_extract_keywords_strips_punctuation():
    result = _extract_keywords("先重构老登录模块！")
    assert "！" not in result
    assert "重构" in result


def test_extract_keywords_max_len():
    result = _extract_keywords("a" * 200)
    assert len(result) == 80


# ============================================================
# detect_verdict — natural_end
# ============================================================

def test_natural_end_with_closing_and_no_mentions():
    verdict = detect_verdict(
        agent_full_text="综上所述，建议先重构登录模块。希望对你有帮助！",
        mentions=[],
        current_agent_id="knowledge",
        depth=0,
    )
    assert verdict.should_terminate is True
    assert verdict.reason == "natural_end"
    assert verdict.warning is None


def test_natural_end_with_closing_and_mentions():
    """有收尾词但也有 @mention → 继续，不终止。"""
    verdict = detect_verdict(
        agent_full_text="综上所述，建议先重构。@review 重构登录模块",
        mentions=[("review", "重构登录模块")],
        current_agent_id="knowledge",
        depth=0,
    )
    assert verdict.should_terminate is False
    assert verdict.reason == "ok"


# ============================================================
# detect_verdict — missing_handoff
# ============================================================

def test_missing_handoff_vague():
    """短/模糊回复 + 无 @mention → missing_handoff。"""
    verdict = detect_verdict(
        agent_full_text="我再想想",
        mentions=[],
        current_agent_id="knowledge",
        depth=0,
    )
    assert verdict.should_terminate is True
    assert verdict.reason == "missing_handoff"
    assert verdict.warning is not None
    assert "看起来不完整" in verdict.warning


def test_missing_handoff_long_no_closing():
    """长回复但无收尾词、无 @mention → natural_end + 温和提示。"""
    long_text = "根据分析，你的笔记库显示..." * 10
    verdict = detect_verdict(
        agent_full_text=long_text,
        mentions=[],
        current_agent_id="knowledge",
        depth=0,
    )
    assert verdict.should_terminate is True
    assert verdict.reason == "natural_end"
    # 长文本但无收尾词 → 温和警告
    assert verdict.warning is not None


# ============================================================
# detect_verdict — loop_detected
# ============================================================

def test_loop_detected_ping_pong():
    """A → B → A 且内容相似 → loop_detected。"""
    history = [
        _HandoffRecord(
            from_agent="knowledge",
            to_agent="review",
            keywords="重构登录模块",
        ),
    ]
    verdict = detect_verdict(
        agent_full_text="分析完成。\n@review 重构登录模块",
        mentions=[("review", "重构登录模块")],
        current_agent_id="knowledge",
        depth=1,
        handoff_history=history,
    )
    assert verdict.should_terminate is True
    assert verdict.reason == "loop_detected"
    assert "循环" in verdict.warning


def test_no_loop_different_content():
    """同一对 Agent 但不同内容 → 不是 loop。"""
    history = [
        _HandoffRecord(
            from_agent="knowledge",
            to_agent="review",
            keywords="重构登录模块",
        ),
    ]
    verdict = detect_verdict(
        agent_full_text="分析完成。\n@review 数据库迁移方案",
        mentions=[("review", "数据库迁移方案")],
        current_agent_id="knowledge",
        depth=1,
        handoff_history=history,
    )
    assert verdict.should_terminate is False


def test_no_loop_first_handoff():
    """第一次 handoff → 不可能是 loop。"""
    verdict = detect_verdict(
        agent_full_text="分析完成。\n@review 这个结论",
        mentions=[("review", "这个结论")],
        current_agent_id="knowledge",
        depth=0,
        handoff_history=[],
    )
    assert verdict.should_terminate is False


# ============================================================
# detect_verdict — max_depth
# ============================================================

def test_max_depth_reached():
    verdict = detect_verdict(
        agent_full_text="分析中...\n@review 继续分析",
        mentions=[("review", "继续分析")],
        current_agent_id="knowledge",
        depth=5,
        max_depth=5,
    )
    assert verdict.should_terminate is True
    assert verdict.reason == "max_depth_reached"
    assert "最大深度" in verdict.warning


# ============================================================
# detect_verdict — depth_warning
# ============================================================

def test_depth_warning():
    """接近上限但未超 → 警告但不终止。"""
    verdict = detect_verdict(
        agent_full_text="分析中...\n@review 继续",
        mentions=[("review", "继续")],
        current_agent_id="knowledge",
        depth=3,
        max_depth=4,
    )
    assert verdict.should_terminate is False
    assert verdict.reason == "depth_warning"
    assert verdict.warning is not None
    assert "接近上限" in verdict.warning


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    tests = [
        # _is_likely_final
        test_is_likely_final_with_closing,
        test_is_likely_final_without_closing,
        # _is_vague
        test_is_vague_short_text,
        test_is_vague_uncertain_phrase,
        test_is_vague_long_clear_text,
        # _extract_keywords
        test_extract_keywords_strips_punctuation,
        test_extract_keywords_max_len,
        # natural_end
        test_natural_end_with_closing_and_no_mentions,
        test_natural_end_with_closing_and_mentions,
        # missing_handoff
        test_missing_handoff_vague,
        test_missing_handoff_long_no_closing,
        # loop_detected
        test_loop_detected_ping_pong,
        test_no_loop_different_content,
        test_no_loop_first_handoff,
        # max_depth
        test_max_depth_reached,
        # depth_warning
        test_depth_warning,
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
