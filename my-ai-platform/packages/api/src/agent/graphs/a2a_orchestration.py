# ============================================================
# A2A Prompt-Chained Orchestration — LangGraph StateGraph 实现
# 对应 MD §3.4 — 跨 Cat 串行路由（Phase 2 才启用）
#
# 诚实命名（MD §3.0）：
#   这不是"Agent 自主路由"。这是 Prompt-Chained Orchestration
#   with Model-Emitted Handoff — 开发者在 system prompt 里教模型
#   用行首 @x 表达 handoff，路由循环是代码在跑，不是模型在"自主决定"。
#
# 图结构：
#   __start__
#       │
#       ▼
#   [router]  ←──────── queue.push(next_cat), depth++
#       │
#       ▼
#   decide_next (条件边)
#       │
#   ┌───┴───┬──────────┐
#   │       │           │
#  "claude" "gpt"    "__end__"
#  (queue   (queue   (queue 空
#   [0])     [0])    或 depth≥15)
#
# parse_a2a_mentions() 是核心 — 约 30 行字符串扫描，
# 判断 Cat 输出里有没有行首 @x，有就 push 到下家。
# 对应 MD §3.4.3 的 9 条规则（前 9 条在此函数内，第 10 条是兄弟模块）。
#
# 安全边界（MD §3.5）：
#   MAX_A2A_DEPTH = 15（Clowder 真实默认）
#   MAX_MENTION_TARGETS = 2（单条消息最多 @ 2 只猫）
#   MAX_TOOL_LOOP_ITERATIONS = 10（建议 8-12）
# ============================================================
