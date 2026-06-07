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
