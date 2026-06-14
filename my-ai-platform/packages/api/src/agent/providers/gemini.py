# ============================================================
# Gemini Adapter — langchain-google-genai 封装（Phase 3 启用）
# 对应 MD §4.1 AgentAdapter 接口 + §4.2 模型角色分工
#
# 角色：联想 + 扩展 + 跨域连接（MD §4.2）
#
# Phase 3 前置条件（MD §9 Phase 3）：
#   黄金集人评里出现 ≥ 5 条"Claude 和 GPT 都没想到、需要联想视角"的样本
#
# 底层：
#   ChatGoogleGenerativeAI (langchain_google_genai)
# ============================================================

import os


def make_gemini(tools: list | None = None):
    """
    返回一个绑定了工具的 ChatGoogleGenerativeAI 实例。
    Phase 3 启用，用于联想扩展 / 头脑风暴场景。

    如果 GEMINI_API_KEY 未配置，resolve_model() 会 fallback 到 DeepSeek。
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. "
            "Gemini provider 需要 GEMINI_API_KEY 环境变量。"
        )

    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=api_key,
        max_tokens=1024,
    )
    if tools:
        return llm.bind_tools(tools)
    return llm
