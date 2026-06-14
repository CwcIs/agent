"""
Router Parser — 纯正则解析函数（零外部依赖，单元测试友好）。

从 router.py 提取出来，避免测试时触发 langgraph 导入链。
"""

import re

MAX_MENTION_TARGETS = 2

# 匹配行首 @agent_id，后接可选空格和观点文本
# 例：@review 早期创业不该做 ToC
_MENTION_RE = re.compile(
    r"(?:^|\n)[ \t]*@([a-zA-Z][a-zA-Z0-9_-]*)(?:[ \t]+(.+))?",
    re.MULTILINE,
)

# 匹配行内 @agent_id（不是行首），用于 shadow detection
# 例："我让 @review 看了一下"、"建议 @review 来挑战这个观点"
_INLINE_MENTION_RE = re.compile(
    r"[^\n@]@([a-zA-Z][a-zA-Z0-9_-]*)",
    re.MULTILINE,
)

# 动作动词——附近出现这些词说明可能是意图性的 handoff
_ACTION_VERBS_RE = re.compile(
    r"(?:帮我|请|让|交给|转给|派给|发给|麻烦|需要.*?看一下|"
    r"让.*?看看|请.*?审|请.*?查|请.*?挑战|让.*?挑战|"
    r"ask|please|let|delegate|hand.?off)",
    re.IGNORECASE,
)

# 匹配用户输入中的 #tag，例：#review
_TAG_RE = re.compile(r"#([a-zA-Z][a-zA-Z0-9_-]*)", re.IGNORECASE)

# 已知的 hashtag → agent_id 映射
_TAG_AGENT_MAP = {
    "review": "review",
    "critique": "review",
}


def parse_user_tags(text: str) -> tuple[str | None, str]:
    """解析用户输入中的 #tag，返回 (agent_id, stripped_text)。"""
    for m in _TAG_RE.finditer(text):
        tag = m.group(1).lower()
        if tag in _TAG_AGENT_MAP:
            stripped = _TAG_RE.sub("", text).strip()
            return _TAG_AGENT_MAP[tag], stripped
    return None, text


def parse_a2a_mentions(
    text: str, current_agent_id: str, valid_agent_ids: list[str]
) -> list[tuple[str, str]]:
    """
    从 Agent 输出文本中解析行首 @mention。
    返回 [(agent_id, content), ...] 列表，最多 MAX_MENTION_TARGETS 条。
    - 过滤掉不存在的 Agent
    - 过滤掉自调用
    - 跳过 fenced code block 内的 @mention
    """
    clean = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    valid_ids = set(valid_agent_ids)
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


def detect_shadow_mentions(
    text: str, current_agent_id: str, valid_agent_ids: list[str]
) -> list[dict]:
    """
    检测行内 @mention（非行首），返回 shadow warning 列表。

    逻辑：
      1. 扫描不在行首的 @agent 提及
      2. 如果附近有动作词（帮我/请/让/交给）→ 发出警告
      3. 如果只是叙述性提及（"我和 @gpt 聊过"）→ 不警告，不路由

    返回 [{"agent_id": str, "content": str, "warning": str}, ...]
    """
    clean = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    valid_ids = set(valid_agent_ids)
    warnings: list[dict] = []

    for m in _INLINE_MENTION_RE.finditer(clean):
        agent_id = m.group(1).lower()

        if agent_id == current_agent_id:
            continue
        if agent_id not in valid_ids:
            continue

        start = max(0, m.start() - 30)
        end = min(len(clean), m.end() + 30)
        context = clean[start:end]

        if _ACTION_VERBS_RE.search(context):
            after_mention = clean[m.end():m.end() + 200].strip()
            content = after_mention.split("\n")[0][:100] if after_mention else ""

            ctx_snippet = context.strip()[:50]
            warnings.append({
                "agent_id": agent_id,
                "content": content,
                "warning": (
                    "Detected inline @{agent} (context: '{ctx}'). "
                    "This looks like an intentional handoff but is not at line start. "
                    "Auto-routed. Consider placing @{agent} at line start explicitly."
                ).format(agent=agent_id, ctx=ctx_snippet),
            })

    return warnings
