# ============================================================
# 场景 C：想法碰撞 — LangGraph StateGraph（Phase 2）
# 对应 MD §2 场景 C + §9 Phase 2 Week 4
#
# 用户提一个新想法 → 语义检索召回 live 笔记 →
# Claude 找支持点 @gpt → GPT 批判 → Claude 综合 →
# 产出 CollisionReport（支持/反对/冲突标记/3 个追问）
#
# 硬约束（MD §2 场景 C）：
#   - 只召回 status=live 的笔记
#   - 每条引用附 noteId + 日期 + confidence(0-1)
#   - 引用到已 superseded 的笔记 → 显式标 conflictWith
#   - 冲突清单主动暴露给用户，要求用户裁决
#
# 图结构：
#   __start__
#       │
#       ▼
#   [search_notes]     — Phase 1: FTS5 关键字 / Phase 2: 向量检索
#       │
#       ▼
#   [claude_support]   — 找支持点，产出 @gpt
#       │
#       ▼
#   should_route? (条件边: parse_a2a_mentions)
#       │
#   ┌───┴───┐
#   │ @gpt  │ 无
#   ▼       ▼
# [gpt_critique]    END
#       │
#       ▼
#   [claude_synthesize] — 综合 → CollisionReport + detectSupersededConflict()
#       │
#       ▼
#   __end__
#
# 这是 Phase 2 A2A 验收的核心链路。
# ============================================================
