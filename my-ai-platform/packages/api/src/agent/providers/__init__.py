# Model Providers — barrel export
# 对应 MD §4.1 AgentAdapter 接口 + §4.2 路由策略
#
# 模型角色分工（MD §4.2）：
#   Claude  → 提炼结构、生成笔记、综合总结（默认入口）
#   GPT     → 批判思维、找漏洞、反驳观点
#   Gemini  → 联想扩展、头脑风暴、跨领域连接
#
# Phase 1 只接 Claude 一家（MD §4.2 重要修正）：
#   三模型分工写出来好看，但感知层只是包装不同 API。
#   Phase 1 就接三家，分不清差异是模型还是 prompt 导致的。
#   多模型推迟到 Phase 2 末尾，且要做 A/B 测试。

from .claude import create_claude_adapter
from .gpt import create_gpt_adapter      # Phase 2
from .gemini import create_gemini_adapter # Phase 3
