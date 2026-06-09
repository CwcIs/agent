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
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
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


# ── DELETE /notes/{id} ────────────────────────────────────
@router.delete("/notes/{note_id}", status_code=200)
def delete_note(note_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = conn.execute("SELECT id FROM notes WHERE id = ? AND deleted_at IS NULL", (note_id,)).fetchone()
    if not row:
        raise HTTPException(404, "note not found")
    conn.execute("UPDATE notes SET deleted_at = datetime('now','localtime') WHERE id = ?", (note_id,))
    conn.commit()
    return {"status": "deleted", "id": note_id}


# ── PATCH /notes/{id} ─────────────────────────────────────
class NotePatch(BaseModel):
    status: str  # archived | live


@router.patch("/notes/{note_id}", status_code=200)
def patch_note(note_id: str, body: NotePatch, conn: sqlite3.Connection = Depends(get_conn)):
    if body.status not in ("archived", "live"):
        raise HTTPException(400, "status must be archived or live")
    row = conn.execute("SELECT id FROM notes WHERE id = ? AND deleted_at IS NULL", (note_id,)).fetchone()
    if not row:
        raise HTTPException(404, "note not found")
    conn.execute("UPDATE notes SET status = ? WHERE id = ?", (body.status, note_id))
    conn.commit()
    return {"status": body.status, "id": note_id}


# ── GET /digest ───────────────────────────────────────────
@router.get("/digest")
async def get_digest(conn: sqlite3.Connection = Depends(get_conn)):
    today = date.today().isoformat()

    # 命中缓存直接返回
    cached = conn.execute(
        "SELECT note_count, narrative, follow_ups, cited_notes FROM daily_digests WHERE date = ?", (today,)
    ).fetchone()
    if cached:
        return {
            "date": today,
            "noteCount": cached[0],
            "narrative": cached[1],
            "followUps": json.loads(cached[2]),
            "citedNotes": json.loads(cached[3]),
        }

    # 取最近 7 天的 live 笔记（没有"昨天"限制，否则新用户永远没数据）
    since = (date.today() - timedelta(days=7)).isoformat()
    rows = conn.execute(
        "SELECT id, title, content, tags_json, created_at FROM notes "
        "WHERE status='live' AND deleted_at IS NULL AND date(created_at) >= ? "
        "ORDER BY created_at DESC LIMIT 20",
        (since,),
    ).fetchall()

    note_count = len(rows)

    # 没有笔记时返回温和提示，不调 LLM
    if note_count == 0:
        result = {
            "date": today,
            "noteCount": 0,
            "narrative": "最近还没有笔记，去 Chat 里写第一条吧。",
            "followUps": ["我想开始记录今天的想法", "帮我新建一条笔记", "笔记库能存什么内容？"],
            "citedNotes": [],
        }
        _cache_digest(conn, today, result)
        return result

    # 组装笔记摘要给 LLM
    notes_text = "\n\n".join(
        f"[{i+1}] id={dict(r)['id']}\n标题：{dict(r)['title']}\n内容：{dict(r)['content'][:300]}"
        for i, r in enumerate(rows)
    )

    prompt = f"""以下是用户最近7天的 {note_count} 条笔记：

{notes_text}

请生成一段连贯的中文综述（不要用 bullet 列表，写成自然段落，150字以内），以及恰好3条值得追问的问题。

以 JSON 格式返回，结构如下：
{{
  "narrative": "综述文字",
  "followUps": ["追问1", "追问2", "追问3"],
  "citedNotes": [{{"noteId": "id", "title": "标题"}}]
}}

只返回 JSON，不要其他文字。"""

    from src.agent.providers.deepseek import make_deepseek
    llm = make_deepseek()
    response = await llm.ainvoke([SystemMessage(content="你是用户的个人知识助手，用中文回答。"), HumanMessage(content=prompt)])

    try:
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        parsed = json.loads(text)
    except Exception:
        parsed = {
            "narrative": response.content[:200],
            "followUps": [],
            "citedNotes": [],
        }

    result = {
        "date": today,
        "noteCount": note_count,
        **parsed,
    }
    _cache_digest(conn, today, result)
    return result


def _cache_digest(conn: sqlite3.Connection, today: str, payload: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO daily_digests (id, date, note_count, narrative, follow_ups, cited_notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            today,
            payload.get("noteCount", 0),
            payload.get("narrative", ""),
            json.dumps(payload.get("followUps", []), ensure_ascii=False),
            json.dumps(payload.get("citedNotes", []), ensure_ascii=False),
        ),
    )
    conn.commit()
