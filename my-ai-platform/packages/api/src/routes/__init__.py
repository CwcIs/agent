# ============================================================
# FastAPI SSE 端点
# 对应 MD §5.3 实时通信（SSE 替代 WebSocket）
#
# 路由：
#   GET  /chat/stream       — SSE 流式响应（LLM token + Agent 切换通知）
#   GET  /notes              — 笔记列表
#   POST /notes              — 保存笔记（备选 REST 入口）
#   GET  /digest             — 每日摘要
#   POST /abort              — 中断请求（Phase 2）
#
# 为什么 SSE 不是 WebSocket（MD §5.3）：
#   Phase 1 只有"服务端推客户端"是高频的，
#   "客户端推服务端"用普通 POST 完全够。
#   SSE 的好处：
#     - 浏览器原生 EventSource，不需要客户端库
#     - 没有握手开销
#     - 自动重连（Last-Event-ID）
#     - 跨代理友好（nginx/Cloudflare 直接过）
#
# FastAPI SSE 实现用 sse-starlette 库
# ============================================================

import json
import sqlite3
import uuid

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

# graph 和 conn 由 main.py lifespan 注入，路由通过依赖获取
_graph = None
_conn: sqlite3.Connection | None = None


def set_globals(graph, conn: sqlite3.Connection) -> None:
    global _graph, _conn
    _graph = graph
    _conn = conn


def get_graph():
    if _graph is None:
        raise HTTPException(500, "graph not initialized")
    return _graph


def get_conn():
    if _conn is None:
        raise HTTPException(500, "db not initialized")
    return _conn


# ── GET /chat/stream ──────────────────────────────────────
@router.get("/chat/stream")
async def chat_stream(
    input: str = "",
    session_id: str = "",
    prompt_version: str = "v1",
    graph=Depends(get_graph),
):
    if not input:
        async def empty_gen():
            yield {"event": "error", "data": "input is required"}
        return EventSourceResponse(empty_gen())

    sid = session_id or str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": sid},
        "recursion_limit": 10,
    }

    async def event_generator():
        try:
            async for event in graph.astream_events(
                {"messages": [HumanMessage(content=input)]},
                config=config,
                version="v2",
            ):
                kind = event["event"]

                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if chunk.content:
                        yield {"event": "token", "data": chunk.content}

                elif kind == "on_tool_start":
                    yield {
                        "event": "tool_start",
                        "data": json.dumps(
                            {"name": event["name"], "input": event["data"].get("input", {})},
                            ensure_ascii=False,
                        ),
                    }

                elif kind == "on_tool_end":
                    output = event["data"].get("output", "")
                    yield {
                        "event": "tool_end",
                        "data": json.dumps(
                            {"name": event["name"], "result": str(output)[:300]},
                            ensure_ascii=False,
                        ),
                    }

            yield {"event": "done", "data": json.dumps({"session_id": sid})}

        except Exception as exc:
            yield {"event": "error", "data": str(exc)}

    return EventSourceResponse(event_generator())


# ── GET /notes ────────────────────────────────────────────
@router.get("/notes")
def list_notes(conn: sqlite3.Connection = Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, title, content, tags_json, status, created_at "
        "FROM notes WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d.pop("tags_json", "[]"))
        result.append(d)
    return {"notes": result}


# ── POST /notes ───────────────────────────────────────────
class NoteIn(BaseModel):
    title: str
    content: str
    tags: str = ""


@router.post("/notes", status_code=201)
def create_note(body: NoteIn, conn: sqlite3.Connection = Depends(get_conn)):
    from src.tools import make_tools
    tools = make_tools(conn)
    save = next(t for t in tools if t.name == "save_note")
    result = save.invoke({"title": body.title, "content": body.content, "tags": body.tags})
    return json.loads(result)
