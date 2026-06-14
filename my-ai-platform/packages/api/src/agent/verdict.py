# ============================================================
# Verdict Detect — A2A 链路终止判定
# 对应 MD §3.6 技术债清单 + Clowder verdict-detect.ts
#
# 防止两个 Agent 互踢皮球（A 说问 B，B 说问 A）和
# AI 写完正文忘记 @mention，链条断在半空。
#
# 三个检测维度（MD §7.5 Phase 2 Week 3 最小实现）：
#   1. natural_end   — 文本像最终答复，自然终止（正常）
#   2. missing_handoff — 无 @mention 且不像最终答复（警告）
#   3. loop_detected  — 同一对 Agent 来回转手（强制终止）
#
# 整合点：router.py:route_serial() 在 parse_a2a_mentions 之后调用。
# ============================================================

import re
from dataclasses import dataclass, field
from typing import Optional

# ── Closing phrases that indicate a natural end ──
# 匹配"不需要继续 @了"的信号词
_CLOSING_PATTERNS = [
    # 中文收尾
    r"综[上所]{1,2}述",
    r"(?:最后|最终|总的)(?:来说|说来|一下|地[，,])?",
    r"以上[所是]",
    r"希望[对这].*?帮助",
    r"如果.*?问题.*?随时",
    r"有.*?问题.*?(?:可以|欢迎|请).*?(?:问|提出|告诉我)",
    r"^(?:完成|结束|完毕|好了?)[。！]",
    r"这就是.*?(?:全部|所有|整个)",
    # 英文收尾
    r"(?:In|To)\s+sum(?:mary|marize)",
    r"Overall[,;]",
    r"I hope this helps",
    r"Let me know if",
    r"Feel free to",
]

_CLOSING_RE = re.compile("|".join(_CLOSING_PATTERNS), re.IGNORECASE)

# ── Vague/uncertain phrases suggesting incomplete answer ──
# 如果回复短且包含这些词，大概率不是最终答案
_VAGUE_PATTERNS = [
    r"我再(?:想想|确认|查)",
    r"让我(?:确认|想想|查|看)",
    r"稍等",
    r"等一下",
    r"让我再",
    r"还不确定",
    r"暂时[没无]",
    r"(?:could|let me)\s+(?:check|think|look)",
    r"not sure yet",
    r"give me a",
]

_VAGUE_RE = re.compile("|".join(_VAGUE_PATTERNS), re.IGNORECASE)

# ── Minimum length to consider a response "complete" ──
_MIN_COMPLETE_CHARS = 80  # 少于 80 字符的回复，没有 @mention 就值得怀疑


@dataclass
class VerdictResult:
    """
    链路终止判定结果。

    should_terminate: True → 路由循环应立即停止
    reason: 终止原因（供日志/可观测性）
    warning: 用户可见的警告消息（None = 无警告）
    """
    should_terminate: bool = False
    reason: str = "ok"
    warning: Optional[str] = None


# ── History fingerprint for loop detection ──
# 记录 (from_agent, to_agent, mention_keywords) 的组合，
# 如果同一组合出现 ≥ 2 次，判定为 loop。
@dataclass
class _HandoffRecord:
    from_agent: str
    to_agent: str
    keywords: str  # mention_content 的前 80 字符，用于相似度比较


def _extract_keywords(text: str, max_len: int = 80) -> str:
    """提取文本的关键词指纹，去掉标点和空白做模糊比较。"""
    cleaned = re.sub(r"[^\w一-鿿]", "", text)
    return cleaned[:max_len].lower()


def _is_likely_final(text: str) -> bool:
    """判断文本是否像最终答复（有收尾信号词）。"""
    if not text:
        return False
    return bool(_CLOSING_RE.search(text))


def _is_vague(text: str) -> bool:
    """判断文本是否模糊/不完整。"""
    if not text:
        return True
    if len(text) < _MIN_COMPLETE_CHARS:
        return True
    return bool(_VAGUE_RE.search(text))


def detect_verdict(
    agent_full_text: str,
    mentions: list[tuple[str, str]],
    current_agent_id: str,
    depth: int,
    max_depth: int = 5,
    handoff_history: Optional[list[_HandoffRecord]] = None,
) -> VerdictResult:
    """
    A2A 链路终止判定。

    参数：
      agent_full_text: Agent 本轮完整输出文本
      mentions: parse_a2a_mentions() 的返回结果 [(target_agent, content), ...]
      current_agent_id: 当前 Agent ID
      depth: 当前链路深度（从 0 开始）
      max_depth: 最大允许深度
      handoff_history: 之前的 handoff 记录（用于 loop detection）

    返回 VerdictResult（should_terminate / reason / warning）。
    """
    if handoff_history is None:
        handoff_history = []

    # ── Check 1: 深度超限（硬终止） ──
    if depth >= max_depth:
        return VerdictResult(
            should_terminate=True,
            reason="max_depth_reached",
            warning=f"A2A 链路已达最大深度 {max_depth}，已自动终止。"
                     f"如有未完成的分析，请手动发起。",
        )

    # ── Check 2: 无 @mention——判断是自然结束还是断了 ──
    if not mentions:
        if _is_likely_final(agent_full_text):
            return VerdictResult(
                should_terminate=True,
                reason="natural_end",
            )
        else:
            # 没有 @mention 且不像最终答案 → 可能断了
            if _is_vague(agent_full_text):
                return VerdictResult(
                    should_terminate=True,
                    reason="missing_handoff",
                    warning=(
                        f"Agent「{current_agent_id}」的回复看起来不完整"
                        f"（{len(agent_full_text)} 字符），"
                        f"且未找到 @mention 交接标记。链路已终止。"
                        f"你可以追问或手动指定下一步。"
                    ),
                )
            else:
                # 长文本但没有 @mention——可能是完整回答忘记 handoff
                # 不强制终止，但打个温和提示
                return VerdictResult(
                    should_terminate=True,
                    reason="natural_end",
                    warning=(
                        f"Agent「{current_agent_id}」已给出较长回复但未指定下一步。"
                        f"链路自然终止。如需继续，可以追问或使用 #review。"
                    ),
                )

    # ── Check 3: Loop detection（ping-pong） ──
    for next_agent, mention_content in mentions:
        keywords = _extract_keywords(mention_content)
        record = _HandoffRecord(
            from_agent=current_agent_id,
            to_agent=next_agent,
            keywords=keywords,
        )

        # 检查是否与历史记录重复
        for prev in handoff_history:
            same_pair = (
                prev.from_agent == current_agent_id
                and prev.to_agent == next_agent
            )
            same_reverse = (
                prev.from_agent == next_agent
                and prev.to_agent == current_agent_id
            )
            similar_content = (
                keywords
                and prev.keywords
                and (keywords in prev.keywords or prev.keywords in keywords)
            )

            if (same_pair or same_reverse) and similar_content:
                return VerdictResult(
                    should_terminate=True,
                    reason="loop_detected",
                    warning=(
                        f"检测到 Agent 循环："
                        f"「{prev.from_agent}」→「{prev.to_agent}」"
                        f"→「{current_agent_id}」→「{next_agent}」。"
                        f"可能两个 Agent 互相踢皮球，链路已终止。"
                        f"请检查问题表述或手动指定分析方向。"
                    ),
                )

        handoff_history.append(record)

    # ── Check 4: 深度预警（接近上限但未超） ──
    if depth >= max_depth - 1:
        return VerdictResult(
            reason="depth_warning",
            warning=f"A2A 链路深度接近上限（{depth + 1}/{max_depth}），"
                    f"下一跳将是最后一轮。",
        )

    # ── All clear ──
    return VerdictResult(reason="ok")
