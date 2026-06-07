# ============================================================
# 场景 A：碎片 → 结构化笔记 — LangGraph StateGraph
# 对应 MD §2 场景 A + §8.2 高频入口
#
# 用户说一段话（会议纪要 / 灵感 / 读书摘要），
# Claude 提炼成 title + summary + tags，写入 SQLite notes 表。
#
# 图结构：
#   __start__
#       │
#       ▼
#   [claude_extract]   — Claude 用 tool_use 提取独立议题
#       │
#       ▼
#   [save_notes]       — 执行 saveNote tool → INSERT INTO notes
#       │
#       ▼
#   __end__
#
# Phase 1 验收（MD §8.3 功能）：
#   输入文字 → Claude 输出 { title, summary, tags } → 写入 SQLite
#
# Phase 1 验收到此为止。多模型分工（GPT 批判 / Gemini 联想）
# 是 Phase 2 的事（MD §4.2）。
# ============================================================
