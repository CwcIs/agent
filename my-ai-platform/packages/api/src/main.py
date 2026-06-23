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

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

load_dotenv()

# ── 1. 启动时校验必填环境变量（fail-fast） ────────────────
_REQUIRED_ENV = ["DEEPSEEK_API_KEY"]

def _check_env() -> None:
    missing = [k for k in _REQUIRED_ENV if not os.getenv(k)]
    if missing:
        print(f"[ERROR] 缺少必填环境变量: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

_check_env()

# ── 2. 初始化 SQLite ──────────────────────────────────────
from src.db.schema import get_conn, init_db

_conn = get_conn()
init_db(_conn)

CHECKPOINT_DB = Path(__file__).parent.parent / "data" / "checkpoint.db"

# ── 3+4. lifespan：启动 AsyncSqliteSaver + 构建 LangGraph 图 ──
from src.agent.registry import init_registry
from src.routes import router, set_globals

@asynccontextmanager
async def lifespan(app: FastAPI):
    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    init_registry(_conn)
    set_globals(_conn)
    yield
    _conn.close()

# ── 5. FastAPI 应用 ───────────────────────────────────────
app = FastAPI(
    title="My AI Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vue dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


def dev():
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    dev()
