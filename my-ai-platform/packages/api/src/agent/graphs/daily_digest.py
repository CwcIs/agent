# ============================================================
# 场景 D：每日 AI 回顾摘要 — LangGraph StateGraph
# 对应 MD §2 场景 D + §8.2 高频入口
#
# 用户每天早上 8 点打开首页，第一屏不是空白对话框，
# 而是 AI 生成的连贯综述 + 恰好 3 条追问。
# 这是整个平台的数据飞轮起点 — 缺它则 Phase 2 向量检索没语料可演。
#
# 图结构：
#   __start__
#       │
#       ▼
#   [fetch_yesterday]  — SELECT * FROM notes WHERE status='live' AND date(created_at)=yesterday
#       │
#       ▼
#   [generate]         — Claude 生成连贯叙述 + 恰好 3 条追问 + 引用附 noteId
#       │
#       ▼
#   [cache]            — 写入 daily_digests 表，同一天再次打开直接读缓存
#       │
#       ▼
#   __end__
#
# Phase 1 取舍（MD §2 场景 D 设计取舍）：
#   - 单模型 Claude 就够，不上三模型分工
#   - "用户每日首次打开"惰性触发 + 缓存，不上 cron
#   - 摘要不入库为 Note，单独存 daily_digests 表
#
# Phase 1 验收（MD §2 场景 D 验收标准）：
#   [ ] 连贯综述不是 bullet 列表
#   [ ] 恰好 3 条追问
#   [ ] 每个引用挂 noteId + 日期
#   [ ] 0 条笔记时温和提示不报错
#   [ ] 同一天再次打开读缓存不重调 LLM
# ============================================================
