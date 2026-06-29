# Model Providers — barrel export
# 对应 MD §4.1 AgentAdapter 接口 + §4.2 路由策略
#
# 模型角色分工（MD §4.2）：
#   DeepSeek → 默认入口、工具调用、综合总结（成本低、工具调用稳定）
#   GPT      → 批判思维、找漏洞、反驳观点
#   Gemini   → 联想扩展、头脑风暴、跨领域连接（Phase 3）
#
# Phase 2 路由策略：
#   resolve_model(agent_id, tools) 按 agent 选择模型，
#   如果首选 provider 的 API key 未配置，fallback 到 DeepSeek。

import logging
import os

from .deepseek import make_deepseek
from .gpt import make_gpt
from .gemini import make_gemini
from .zhipu import make_zhipu

logger = logging.getLogger(__name__)

# agent_id → (provider_name, make_fn)
_AGENT_MODEL_MAP: dict[str, tuple[str, object]] = {
    "knowledge": ("deepseek", make_deepseek),
    "review":    ("zhipu",   make_zhipu),
    "brain":     ("gemini",  make_gemini),
}

_DEFAULT_PROVIDER = make_deepseek


def _check_provider_available(name: str) -> bool:
    """检查 provider 的 API key 是否已配置。"""
    key_map = {
        "deepseek": "DEEPSEEK_API_KEY",
        "gpt":      "OPENAI_API_KEY",
        "gemini":   "GEMINI_API_KEY",
        "zhipu":    "ZHIPU_API_KEY",
    }
    env_key = key_map.get(name)
    if env_key is None:
        return False
    return bool(os.environ.get(env_key))


def resolve_model(agent_id: str, tools: list | None = None):
    """
    按 agent_id 选择模型 provider，带 fallback 逻辑。

    规则：
      - knowledge  → DeepSeek（默认）
      - review     → GPT（批判思维），若 OPENAI_API_KEY 未配置 → fallback DeepSeek
      - 未知 agent → DeepSeek

    返回绑定了 tools 的 ChatModel 实例。
    """
    provider_name, make_fn = _AGENT_MODEL_MAP.get(agent_id, ("deepseek", make_deepseek))

    if _check_provider_available(provider_name):
        logger.info("resolve_model agent=%s → %s", agent_id, provider_name)
    else:
        logger.warning(
            "resolve_model agent=%s → %s (unavailable, fallback → deepseek)",
            agent_id, provider_name,
        )
        provider_name = "deepseek"
        make_fn = make_deepseek

    return make_fn(tools)
