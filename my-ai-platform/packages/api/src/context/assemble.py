# ============================================================
# 记忆三层组装 — assembleContext()
# 对应 MD §4.4 记忆三层架构
#
# 分层逻辑在 Assembler，不在 Store（MD §4.4 重要修正）：
#   Clowder 的 RedisMessageStore.ts 只是底层存储后端，
#   真正的分层逻辑在 ContextAssembler.ts + context-transport.ts
#
# 三层（MD §4.4 表）：
#   工作记忆 — 最近 N 轮对话（SQLite messages 表按 session_id 取最新 20 条）
#   情节记忆 — 笔记 + 历史（SQLite notes 表 + FTS5 关键字 / 向量检索）
#   语义记忆 — 向量检索（Phase 2 note_embeddings + sqlite-vec，Phase 1 不打开）
#
# Phase 1 极简版（MD §4.4 伪代码）：
#   working  = db.recentMessages(sessionId, 20)
#   episodic = db.searchNotesFTS(userInput, 5)
#   // semantic = vec.search(userInput, 5)  // Phase 2
#   return [system(episodic), ...working, user]
#
# 注意（MD §4.6）：
#   sessionId + promptVersion 一起贯穿 → system prompt 拼接时带版本号
# ============================================================
