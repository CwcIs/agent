# Agent 层 — barrel export

# 核心认知（MD §3.0）：
#   主轴 A: ReAct Tool Loop（单 Cat 内，模型自己决定调不调工具）
#   主轴 B: Prompt-Chained Handoff（跨 Cat，Router 做字符串匹配调度）
#   前者是 Agent，后者是 orchestration
