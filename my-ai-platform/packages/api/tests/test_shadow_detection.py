"""
A2A Shadow Detection 单元测试。

测试 detect_shadow_mentions() 和 parse_a2a_mentions() 的行为。
所有函数位于 router_parser.py（零外部依赖，可直接测试）。

运行方式：
  cd packages/api
  python tests/test_shadow_detection.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.router_parser import detect_shadow_mentions, parse_a2a_mentions

_IDS = ["knowledge", "review"]


# ============================================================
# Shadow Detection
# ============================================================

def test_no_shadow_for_line_start():
    """行首 @mention 不应被检测为 shadow。"""
    text = "分析完成。\n@review 这个结论需要挑战"
    shadows = detect_shadow_mentions(text, "knowledge", _IDS)
    assert shadows == [], f"Expected empty, got {shadows}"


def test_shadow_with_action_verb():
    """行内 @mention + 动作词（让）→ shadow warning。"""
    text = "我让 @review 看了一下这个结论"
    shadows = detect_shadow_mentions(text, "knowledge", _IDS)
    assert len(shadows) >= 1, f"Expected shadow warning, got {shadows}"
    assert shadows[0]["agent_id"] == "review"
    assert "inline" in shadows[0]["warning"].lower()


def test_shadow_with_qing():
    """行内 @mention + '请' → shadow warning。"""
    text = "建议请 @review 来挑战这个观点，看看有没有漏洞"
    shadows = detect_shadow_mentions(text, "knowledge", _IDS)
    assert len(shadows) >= 1


def test_no_shadow_narrative_mention():
    """叙述性提及（无动作词）→ 不 shadow。"""
    text = "我之前和 @review 讨论过这个问题，它的回复是..."
    shadows = detect_shadow_mentions(text, "knowledge", _IDS)
    assert shadows == [], f"Expected empty for narrative mention, got {shadows}"


def test_shadow_ignores_self_mention():
    """Agent 不能 shadow 自己。"""
    text = "我让 @knowledge 看了一下"
    shadows = detect_shadow_mentions(text, "knowledge", _IDS)
    assert shadows == []


def test_shadow_ignores_code_block():
    """Fenced code block 内的 mention 应被忽略。"""
    text = "```python\n# @review is called here\n```\n\n我让 @review 看看"
    shadows = detect_shadow_mentions(text, "knowledge", _IDS)
    assert len(shadows) == 1  # 只有外面的 @review


def test_shadow_ignores_unknown_agent():
    """不存在的 agent id 不应产生 shadow。"""
    text = "我让 @unknownbot 看了一下，它说没问题"
    shadows = detect_shadow_mentions(text, "knowledge", _IDS)
    assert shadows == []


# ============================================================
# Line-start parser unchanged behavior
# ============================================================

def test_line_start_parser_still_works():
    """行首 parser 不受 shadow detection 影响。"""
    text = "分析完成。\n@review 这个观点"
    mentions = parse_a2a_mentions(text, "knowledge", _IDS)
    assert len(mentions) == 1
    assert mentions[0] == ("review", "这个观点")


def test_line_start_parser_filters_self():
    """行首 parser 过滤自调用。"""
    text = "@knowledge 我该怎么做"
    mentions = parse_a2a_mentions(text, "knowledge", _IDS)
    assert len(mentions) == 0


def test_line_start_parser_filters_unknown():
    """行首 parser 过滤不存在的 agent。"""
    text = "@unknownbot 帮我分析"
    mentions = parse_a2a_mentions(text, "knowledge", _IDS)
    assert len(mentions) == 0


def test_both_line_start_and_shadow():
    """混合场景：同时有行首和行内 mention。"""
    text = "我让 @review 先看看\n\n@review 正式挑战这个观点"
    mentions = parse_a2a_mentions(text, "knowledge", _IDS)
    assert len(mentions) >= 1
    shadows = detect_shadow_mentions(text, "knowledge", _IDS)
    assert len(shadows) >= 1


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    tests = [
        test_no_shadow_for_line_start,
        test_shadow_with_action_verb,
        test_shadow_with_qing,
        test_no_shadow_narrative_mention,
        test_shadow_ignores_self_mention,
        test_shadow_ignores_code_block,
        test_shadow_ignores_unknown_agent,
        test_line_start_parser_still_works,
        test_line_start_parser_filters_self,
        test_line_start_parser_filters_unknown,
        test_both_line_start_and_shadow,
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
