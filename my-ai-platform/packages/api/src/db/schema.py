# ============================================================
# SQLite 6 表 Schema（Phase 1）
# 对应 MD §8.5 Phase 1 全部表 + §4.3 数据模型
#
# 表：
#   1. notes           — 笔记主表（status / superseded_by / deleted_at）
#   2. messages        — 对话消息（session_id / agent_id / prompt_version）
#   3. daily_digests   — 每日 AI 回顾（惰性触发 + 缓存）
#   4. llm_calls       — LLM 调用审计（计费 + 重试 + 排查）
#   5. llm_errors      — JSON 解析 / tool_use 失败记录
#   6. eval_runs       — 黄金集运行记录
#
# 附：
#   notes_fts (FTS5)   — Phase 1 关键字全文检索
#   note_embeddings    — Phase 2 向量（sqlite-vec）
#   embedding_meta     — Phase 2 embedding 指纹（model_id / dim / prompt_version）
#
# 为什么这 6 张？（MD §8.5）：
#   notes / messages 是业务，剩下 4 张全是工程兜底。
#   没有它们就只能"感觉"AI 在变好，没法量化。
#   Phase 1 就要把"可观测"扎进 schema，不等 Phase 3 才补。
#
# 为什么 embedding 拆出去？（MD §4.3）：
#   Phase 2 换 embedding 模型时，向量塞在 notes 里要全表回填。
#   拆成独立表 + embedding_meta 指纹，换模型时新增一行 meta、
#   后台慢慢回算，老向量继续服务旧查询。
# ============================================================
