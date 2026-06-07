# ============================================================
# ReAct Tool Loop — LangGraph StateGraph 实现
# 对应 MD §3.3 — 单 Cat 内 Thought → Action → Observation 循环
#
# 这是整个平台 Agent 原理的核心，Phase 1 必须跑通。
# 没有 tool loop 跑通，Phase 1 验收不算过。
#
# 图结构（LangGraph StateGraph）：
#   __start__
#       │
#       ▼
#   [call_model]  ←──────────────┐
#       │                        │
#       ▼                        │
#   should_continue?             │
#   has tool_calls?              │
#       │                        │
#   ┌───┴───┐                    │
#   │ YES   │ NO                 │
#   ▼       ▼                    │
# [tools]  END                   │
#   │                            │
#   └────────────────────────────┘
#
# 对应 MD §8.6 的伪代码 runReActLoop()，LangGraph 把它画成了图：
#   - StateGraph 节点 = [stream] → [check_tool_use] → [run_tools] → 回到 [stream]
#   - 条件边 = should_continue 判断最后一条消息是否有 tool_calls
#   - MAX_TOOL_LOOP_ITERATIONS 通过 LangGraph recursion_limit 控制
#
# Phase 1 验收（MD §8.3 Agent 原理）：
#   注册两个工具 searchNotes + saveNote，给 Claude 一句需要两跳的话：
#   "把我刚说的'B 端优先'整理成笔记，但先看看我之前对 B 端有没有写过什么。"
#   期待 chunk 序列：
#     tool_use(searchNotes) → tool_result → text("找到 3 条...")
#     → tool_use(saveNote) → tool_result → text("已保存")
#   这串序列出现一次，"我懂 Agent 是怎么自己干活的"才算落地。
# ============================================================
