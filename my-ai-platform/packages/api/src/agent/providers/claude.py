# ============================================================
# Claude Adapter — langchain-anthropic 封装
# 对应 MD §4.1 AgentAdapter 接口 + §4.2 模型角色分工
#
# 角色：提炼 + 写作 + 综合（MD §4.2）
# Phase 1 唯一入口 — 三模型分工推迟到 Phase 2（MD §4.2 重要修正）
#
# 接口：
#   invoke(messages, tools) → AsyncIterable[AgentChunk]
#   AgentChunk 三件套：text / tool_use / tool_result（MD §4.1）
#
# 底层：
#   ChatAnthropic (langchain_anthropic)
#   一次 messages.create / stream 调用本身不循环，
#   循环在 react_tool_loop.py 的 runToolLoop（MD §3.3.2）
# ============================================================

import os

from langchain_anthropic import ChatAnthropic


def make_claude(tools: list | None = None) -> ChatAnthropic:
    """
    返回一个绑定了工具的 ChatAnthropic 实例。
    Phase 1 用 claude-3-5-haiku（速度快、成本低）。
    """
    llm = ChatAnthropic(
        model="claude-3-5-haiku-20241022",
        api_key=os.environ["ANTHROPIC_API_KEY"],
        max_tokens=1024,
    )
    if tools:
        return llm.bind_tools(tools)
    return llm
