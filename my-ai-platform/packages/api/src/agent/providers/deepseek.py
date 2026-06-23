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

from langchain_openai import ChatOpenAI


def make_deepseek(tools: list | None = None) -> ChatOpenAI:
    """
    返回一个绑定了工具的 ChatOpenAI 实例（指向 DeepSeek）。
    Phase 1 用 deepseek-chat（成本低、工具调用稳定）。
    """
    llm = ChatOpenAI(
        model="deepseek-chat",
        openai_api_key=os.environ["DEEPSEEK_API_KEY"],
        openai_api_base="https://api.deepseek.com",
        max_tokens=1024,
    )
    if tools:
        return llm.bind_tools(tools)
    return llm
