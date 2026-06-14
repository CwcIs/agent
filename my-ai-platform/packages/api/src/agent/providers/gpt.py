# ============================================================
# GPT Adapter — langchain-openai 封装（Phase 2 启用）
# 对应 MD §4.1 AgentAdapter 接口 + §4.2 模型角色分工
#
# 角色：批判 + 反驳 + 严密论证（MD §4.2）
# 用于 ReviewAgent 的思维挑战场景
#
# 重要（MD §9 Phase 2 Week 2）：
#   Phase 2 接 GPT 时不要直接上 A2A — 先把 GPT 当独立 Agent 跑顺，
#   再加路由。否则一旦 A2A 链坏了，分不清是 GPT 接入问题还是路由问题。
#
# 底层：
#   ChatOpenAI (langchain_openai)
#   签名和 ChatAnthropic 一致（AgentAdapter 接口统一）
# ============================================================

import os

from langchain_openai import ChatOpenAI


def make_gpt(tools: list | None = None) -> ChatOpenAI:
    """
    返回一个绑定了工具的 ChatOpenAI 实例（指向 OpenAI GPT-4o-mini）。
    Phase 2 ReviewAgent 优先用 GPT 做批判思维；
    如果 OPENAI_API_KEY 未配置，resolve_model() 会 fallback 到 DeepSeek。
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. "
            "ReviewAgent 需要 GPT 做批判思维，但 OpenAI key 未配置。"
        )

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        openai_api_key=api_key,
        max_tokens=1024,
    )
    if tools:
        return llm.bind_tools(tools)
    return llm
