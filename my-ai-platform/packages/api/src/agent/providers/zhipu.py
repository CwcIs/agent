# ============================================================
# 智谱 (Zhipu/GLM) Adapter — langchain-openai 封装
#
# 角色：批判 + 反驳 + 严密论证（替代 GPT 用于 ReviewAgent）
# 智谱 API 完全兼容 OpenAI 接口格式，直接用 ChatOpenAI。
#
# 模型选择：
#   glm-4-flash — 免费，适合 review 场景（速度优先）
#   如需更强推理可切换 glm-4-plus
#
# 文档：https://open.bigmodel.cn/dev/api/normal-model/glm-4
# ============================================================

import os

from langchain_openai import ChatOpenAI


def make_zhipu(tools: list | None = None) -> ChatOpenAI:
    """
    返回一个绑定了工具的 ChatOpenAI 实例（指向智谱 GLM-4-Flash）。
    ReviewAgent 使用智谱做批判思维；
    如果 ZHIPU_API_KEY 未配置，resolve_model() 会 fallback 到 DeepSeek。
    """
    api_key = os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ZHIPU_API_KEY not set. "
            "ReviewAgent 需要智谱做批判思维，但 Zhipu key 未配置。"
        )

    llm = ChatOpenAI(
        model="glm-4-flash",
        openai_api_key=api_key,
        openai_api_base="https://open.bigmodel.cn/api/paas/v4",
        max_tokens=1024,
    )
    if tools:
        return llm.bind_tools(tools)
    return llm
