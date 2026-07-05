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

_conn: sqlite3.Connection | None = None


def set_globals(conn: sqlite3.Connection) -> None:
    global _conn
    _conn = conn


def get_conn():
    if _conn is None:
        raise HTTPException(500, "db not initialized")
    return _conn


# ── Shared SSE event generator ─────────────────────────────
def _build_sse_generator(user_input: str, session_id: str, prompt_version: str, trace_id: str):
    """构建 SSE 事件生成器，GET 和 POST 共用。"""
    async def event_generator():
        from src.db.schema import get_conn as new_conn
        stream_conn = new_conn()
        from src.agent.router import route_serial
        try:
            async for event in route_serial(user_input, session_id, conn=stream_conn, prompt_version=prompt_version, trace_id=trace_id):
                etype = event.get("type")

                if etype == "token":
                    yield {
                        "event": "token",
                        "data": json.dumps(
                            {"delta": event["delta"], "agentId": event["agentId"]},
                            ensure_ascii=False,
                        ),
                    }

                elif etype == "tool_start":
                    yield {
                        "event": "tool_start",
                        "data": json.dumps(
                            {
                                "name": event["name"],
                                "input": event.get("input", {}),
                                "agentId": event["agentId"],
                            },
                            ensure_ascii=False,
                        ),
                    }

                elif etype == "tool_end":
                    yield {
                        "event": "tool_end",
                        "data": json.dumps(
                            {
                                "name": event["name"],
                                "result": event.get("result", ""),
                                "agentId": event["agentId"],
                            },
                            ensure_ascii=False,
                        ),
                    }

                elif etype == "agent_switch":
                    yield {
                        "event": "agent_switch",
                        "data": json.dumps({"agentId": event["agentId"]}, ensure_ascii=False),
                    }

                elif etype == "done":
                    # 跳过 BaseAgent.astream 发出的 agent 级别 done（无 trace_id），
                    # 只透传 route_serial 的最终 done（携带完整 trace_id）
                    if not event.get("trace_id"):
                        continue
                    yield {"event": "done", "data": json.dumps({"session_id": session_id, "trace_id": event.get("trace_id", "")})}

                elif etype == "error":
                    yield {"event": "error", "data": event.get("message", "unknown error")}

        except Exception as exc:
            yield {"event": "error", "data": str(exc)}
        finally:
            stream_conn.close()

    return event_generator()


class ChatStreamBody(BaseModel):
    input: str
    session_id: str = ""
    prompt_version: str = "v1"


# ── POST /chat/stream ─────────────────────────────────────
@router.post("/chat/stream")
async def chat_stream_post(body: ChatStreamBody):
    """POST 版本 — input 在 body 中，避免长文本导致 URL 截断 → 431。"""
    if not body.input:
        async def empty_gen():
            yield {"event": "error", "data": "input is required"}
        return EventSourceResponse(empty_gen())

    sid = body.session_id or str(uuid.uuid4())
    tid = str(uuid.uuid4())
    return EventSourceResponse(_build_sse_generator(body.input, sid, body.prompt_version, tid))


# ── GET /chat/stream（保留兼容）────────────────────────────
@router.get("/chat/stream")
async def chat_stream_get(
    input: str = "",
    session_id: str = "",
    prompt_version: str = "v1",
):
    """GET 版本 — 保留兼容，短文本仍可用。"""
    if not input:
        async def empty_gen():
            yield {"event": "error", "data": "input is required"}
        return EventSourceResponse(empty_gen())

    sid = session_id or str(uuid.uuid4())
    tid = str(uuid.uuid4())
    return EventSourceResponse(_build_sse_generator(input, sid, prompt_version, tid))


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
            "trends": json.loads(cached["trends"] if "trends" in cached.keys() else "[]"),
            "anomalies": json.loads(cached["anomalies"] if "anomalies" in cached.keys() else "[]"),
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
            "trends": [],
            "anomalies": [],
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
    # 趋势检测（纯数据计算，不调 LLM）
    patterns = _detect_trends(conn, rows)
    result["trends"] = patterns["trends"]
    result["anomalies"] = patterns["anomalies"]
    _cache_digest(conn, today, result)
    return result


# ── GET /notes/{id}/relations ─────────────────────────────────
@router.get("/notes/{note_id}/relations")
def get_note_relations(note_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """返回一条笔记的所有关系（出链 + 入链）。"""
    outgoing = conn.execute(
        """
        SELECT e.id, e.to_id, n.title as to_title, e.relation, e.created_at
        FROM edges e
        JOIN notes n ON n.id = e.to_id
        WHERE e.from_id = ? AND n.deleted_at IS NULL
        ORDER BY e.created_at DESC
        """,
        (note_id,),
    ).fetchall()

    incoming = conn.execute(
        """
        SELECT e.id, e.from_id, n.title as from_title, e.relation, e.created_at
        FROM edges e
        JOIN notes n ON n.id = e.from_id
        WHERE e.to_id = ? AND n.deleted_at IS NULL
        ORDER BY e.created_at DESC
        """,
        (note_id,),
    ).fetchall()

    return {
        "note_id": note_id,
        "outgoing": [{"id": r[0], "to_id": r[1], "to_title": r[2], "relation": r[3], "created_at": r[4]} for r in outgoing],
        "incoming": [{"id": r[0], "from_id": r[1], "from_title": r[2], "relation": r[3], "created_at": r[4]} for r in incoming],
    }


# ── GET /trace/{trace_id} ────────────────────────────────────
@router.get("/trace/{trace_id}")
def get_trace(trace_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, session_id, agent_id, model, input_tokens, output_tokens, "
        "cost_usd, latency_ms, status, created_at "
        "FROM llm_calls WHERE trace_id = ? ORDER BY created_at ASC",
        (trace_id,),
    ).fetchall()
    calls = [dict(r) for r in rows]

    # 按 agent_id 分组，保持首次出现顺序
    groups: dict[str, list] = {}
    for c in calls:
        aid = c["agent_id"] or "unknown"
        groups.setdefault(aid, []).append(c)

    agents = []
    for aid, agent_calls in groups.items():
        agents.append({
            "agent_id": aid,
            "calls": agent_calls,
            "subtotal": {
                "tokens": sum(c["input_tokens"] + c["output_tokens"] for c in agent_calls),
                "cost_usd": round(sum(c["cost_usd"] for c in agent_calls), 6),
                "latency_ms": sum(c["latency_ms"] for c in agent_calls),
                "call_count": len(agent_calls),
            },
        })

    return {
        "trace_id": trace_id,
        "agents": agents,
        "summary": {
            "total_tokens": sum(c["input_tokens"] + c["output_tokens"] for c in calls),
            "total_cost_usd": round(sum(c["cost_usd"] for c in calls), 6),
            "total_latency_ms": sum(c["latency_ms"] for c in calls),
            "call_count": len(calls),
        },
    }


def _cache_digest(conn: sqlite3.Connection, today: str, payload: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO daily_digests "
        "(id, date, note_count, narrative, follow_ups, cited_notes, trends, anomalies) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            today,
            payload.get("noteCount", 0),
            payload.get("narrative", ""),
            json.dumps(payload.get("followUps", []), ensure_ascii=False),
            json.dumps(payload.get("citedNotes", []), ensure_ascii=False),
            json.dumps(payload.get("trends", []), ensure_ascii=False),
            json.dumps(payload.get("anomalies", []), ensure_ascii=False),
        ),
    )
    conn.commit()


def _detect_trends(conn: sqlite3.Connection, note_rows: list) -> dict:
    """
    分析笔记创建模式，检测趋势和异常。
    纯数据计算，不调用 LLM。
    """
    if len(note_rows) < 2:
        return {"trends": [], "anomalies": []}

    from collections import defaultdict

    # 按天分组 + 标签统计
    by_day: dict[str, int] = defaultdict(int)
    by_tag: dict[str, int] = defaultdict(int)
    for r in note_rows:
        d = dict(r)
        day = d["created_at"][:10]
        by_day[day] += 1
        for tag in json.loads(d.get("tags_json", "[]")):
            by_tag[tag] += 1

    trends: list[str] = []
    anomalies: list[str] = []

    # 频率趋势：前半 vs 后半
    sorted_days = sorted(by_day.keys())
    if len(sorted_days) >= 3:
        mid = len(sorted_days) // 2
        first_half = sum(by_day[d] for d in sorted_days[:mid])
        second_half = sum(by_day[d] for d in sorted_days[mid:])
        if first_half > 0 and second_half > first_half * 1.5:
            trends.append(f"笔记频率上升：后段 {second_half} 条 vs 前段 {first_half} 条")
        elif second_half > 0 and first_half > second_half * 1.5:
            trends.append(f"笔记频率下降：后段 {second_half} 条 vs 前段 {first_half} 条")

    # 标签热度
    hot_tags = [(tag, count) for tag, count in sorted(by_tag.items(), key=lambda x: (-x[1], x[0])) if count >= 3]
    for tag, count in hot_tags:
        trends.append(f"关注话题「{tag}」出现 {count} 次")

    # 异常空白日（活跃日之间有 0 笔记的日期，最多报 2 个）
    if len(sorted_days) >= 3:
        from datetime import date as dt, timedelta
        active_set = set(sorted_days)
        start = dt.fromisoformat(sorted_days[0])
        end = dt.fromisoformat(sorted_days[-1])
        d = start
        while d <= end:
            day_str = d.isoformat()
            if day_str not in active_set and day_str != dt.today().isoformat():
                anomalies.append(f"{day_str} 无新笔记")
                if len(anomalies) >= 2:
                    break
            d += timedelta(days=1)

    return {"trends": trends[:5], "anomalies": anomalies[:3]}
