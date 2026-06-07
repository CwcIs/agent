# ============================================================
# GPT Adapter — langchain-openai 封装（Phase 2 启用）
# 对应 MD §4.1 AgentAdapter 接口 + §4.2 模型角色分工
#
# 角色：批判 + 反驳 + 严密论证（MD §4.2）
#
# 重要（MD §9 Phase 2 Week 2）：
#   Phase 2 接 GPT 时不要直接上 A2A — 先把 GPT 当独立 Agent 跑顺，
#   再加路由。否则一旦 A2A 链坏了，分不清是 GPT 接入问题还是路由问题。
#
# 底层：
#   ChatOpenAI (langchain_openai)
#   签名和 ChatAnthropic 一致（AgentAdapter 接口统一）
# ============================================================
