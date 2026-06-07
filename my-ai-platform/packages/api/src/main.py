# ============================================================
# 应用入口 — FastAPI + LangGraph
# 对应 MD：
#   §3.1 三层结构（平台层 + 模型层）
#   §5.1 技术选型（Fastify → 这里改用 FastAPI）
#   §5.5 工程基础（.env Zod 校验 → 这里用 Pydantic Settings）
#   §8.4 W1 里程碑（骨架立起来）
#
# 启动流程：
#   1. 校验 .env 必填项（缺 key → fail-fast exit(1)）
#   2. 初始化 SQLite（db/schema.py 六张表）
#   3. 注册 FastAPI 路由（routes/ → SSE + REST）
#   4. 注册 LangGraph 图（agent/graphs/）
#   5. uvicorn 启动
# ============================================================
