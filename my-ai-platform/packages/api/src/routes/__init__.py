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
                        "data": json.dumps(
                            {
                                "agentId": event["agentId"],
                                "trace_id": event.get("trace_id", ""),
                            },
                            ensure_ascii=False,
                        ),
                    }

                elif etype == "done":
                    # 跳过 BaseAgent.astream 发出的 agent 级别 done（无 trace_id），
                    # 只透传 route_serial 的最终 done（携带完整 trace_id + phase_trace_ids）
                    if not event.get("trace_id"):
                        continue
                    done_data = {"session_id": session_id, "trace_id": event.get("trace_id", "")}
                    if event.get("phase_trace_ids"):
                        done_data["phase_trace_ids"] = event["phase_trace_ids"]
                    yield {"event": "done", "data": json.dumps(done_data)}

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


# ── Shared digest builder ───────────────────────────────────
async def _build_digest(conn: sqlite3.Connection, days: int, label: str) -> dict:
    """通用 digest 构建器：daily(7天) / weekly(30天) / monthly(90天)。"""
    since = (date.today() - timedelta(days=days)).isoformat()
    limit = 50 if days >= 30 else 30
    rows = conn.execute(
        "SELECT id, title, content, tags_json, created_at FROM notes "
        "WHERE status='live' AND deleted_at IS NULL AND date(created_at) >= ? "
        "ORDER BY created_at DESC LIMIT ?",
        (since, limit),
    ).fetchall()

    note_count = len(rows)

    if note_count == 0:
        return {
            "label": label,
            "noteCount": 0,
            "narrative": "这个时间段还没有笔记，去 Chat 里写一条吧。",
            "followUps": ["我想开始记录想法", "帮我新建一条笔记", "笔记库能存什么内容？"],
            "citedNotes": [],
            "trends": [],
            "anomalies": [],
            "collisions": [],
        }

    notes_text = "\n\n".join(
        f"[{i+1}] id={dict(r)['id']}\n标题：{dict(r)['title']}\n内容：{dict(r)['content'][:300]}"
        for i, r in enumerate(rows)
    )

    prompt = f"""以下是用户最近 {days} 天的 {note_count} 条笔记：

{notes_text}

请生成：
1. 一段中文综述（自然段落，150字以内），指出知识演进或话题迁移
2. 恰好3条值得追问的问题
3. 1-2个趋势发现（如"话题X反复出现"、"从A→B→C的知识演进"）
4. 1-2个值得探索的方向

以 JSON 格式返回：
{{
  "narrative": "综述文字",
  "followUps": ["追问1", "追问2", "追问3"],
  "citedNotes": [{{"noteId": "id", "title": "标题"}}],
  "trends": ["趋势发现1", "趋势发现2"],
  "explore": ["值得探索的方向1"]
}}

只返回 JSON。"""

    from src.agent.providers.deepseek import make_deepseek
    llm = make_deepseek()
    try:
        response = await llm.ainvoke([SystemMessage(content="你是用户的个人知识助手，用中文回答。"), HumanMessage(content=prompt)])
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        parsed = json.loads(text)
    except Exception:
        parsed = {
            "narrative": response.content[:200] if 'response' in dir() else "分析生成失败",
            "followUps": [],
            "citedNotes": [],
            "trends": [],
            "explore": [],
        }

    # 获取碰撞发现
    collision_rows = conn.execute(
        "SELECT id, note_a_id, note_b_id, score, connection, angle FROM idea_collisions "
        "WHERE created_at >= ? ORDER BY score DESC LIMIT 5",
        (since,),
    ).fetchall()

    # 异常检测（纯数据，不调 LLM）
    anomalies = _detect_anomalies_basic(conn, rows)

    return {
        "label": label,
        "noteCount": note_count,
        "narrative": parsed.get("narrative", ""),
        "followUps": parsed.get("followUps", []),
        "citedNotes": parsed.get("citedNotes", []),
        "trends": parsed.get("trends", []) + parsed.get("explore", []),
        "anomalies": anomalies,
        "collisions": [
            {
                "id": r["id"],
                "note_a_id": r["note_a_id"],
                "note_b_id": r["note_b_id"],
                "score": r["score"],
                "connection": r["connection"],
                "angle": r["angle"],
            }
            for r in collision_rows
        ],
    }


def _detect_anomalies_basic(conn: sqlite3.Connection, note_rows: list) -> list[str]:
    """简单异常检测：空白日 + 笔记爆发。纯数据计算。"""
    if len(note_rows) < 2:
        return []
    from collections import defaultdict
    by_day: dict[str, int] = defaultdict(int)
    for r in note_rows:
        day = dict(r)["created_at"][:10]
        by_day[day] += 1
    sorted_days = sorted(by_day.keys())
    anomalies: list[str] = []
    # 空白日
    if len(sorted_days) >= 3:
        start = date.fromisoformat(sorted_days[0])
        end = date.fromisoformat(sorted_days[-1])
        d = start
        while d <= end:
            if d.isoformat() not in by_day and d != date.today():
                anomalies.append(f"{d.isoformat()} 无新笔记")
                if len(anomalies) >= 2:
                    break
            d += timedelta(days=1)
    return anomalies[:3]


# ── GET /digest (daily) ───────────────────────────────────
@router.get("/digest")
async def get_digest(conn: sqlite3.Connection = Depends(get_conn)):
    today = date.today().isoformat()

    # 命中缓存直接返回
    cached = conn.execute(
        "SELECT note_count, narrative, follow_ups, cited_notes, trends, anomalies FROM daily_digests WHERE date = ?", (today,)
    ).fetchone()
    if cached:
        return {
            "label": "daily",
            "date": today,
            "noteCount": cached["note_count"],
            "narrative": cached["narrative"],
            "followUps": json.loads(cached["follow_ups"]),
            "citedNotes": json.loads(cached["cited_notes"]),
            "trends": json.loads(cached["trends"] if cached["trends"] else "[]"),
            "anomalies": json.loads(cached["anomalies"] if cached["anomalies"] else "[]"),
            "collisions": [],
        }

    result = await _build_digest(conn, 7, "daily")
    result["date"] = today
    _cache_digest(conn, today, result)
    return result


# ── GET /digest/weekly ────────────────────────────────────
@router.get("/digest/weekly")
async def get_weekly_digest(conn: sqlite3.Connection = Depends(get_conn)):
    """周回顾：最近 30 天笔记的 LLM 分析。"""
    return await _build_digest(conn, 30, "weekly")


# ── GET /digest/monthly ───────────────────────────────────
@router.get("/digest/monthly")
async def get_monthly_digest(conn: sqlite3.Connection = Depends(get_conn)):
    """月回顾：最近 90 天笔记的 LLM 分析。"""
    return await _build_digest(conn, 90, "monthly")


# ── GET /notes/{id}/relations ─────────────────────────────────
@router.get("/notes/{note_id}/relations")
def get_note_relations(note_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """返回一条笔记的所有关系（出链 + 入链）。"""
    outgoing = conn.execute(
        """
        SELECT e.id, e.to_id, n.title as to_title, e.relation, e.confidence,
               e.source, e.evidence, e.status, e.created_at
        FROM edges e
        JOIN notes n ON n.id = e.to_id
        WHERE e.from_id = ? AND n.deleted_at IS NULL
        ORDER BY e.created_at DESC
        """,
        (note_id,),
    ).fetchall()

    incoming = conn.execute(
        """
        SELECT e.id, e.from_id, n.title as from_title, e.relation, e.confidence,
               e.source, e.evidence, e.status, e.created_at
        FROM edges e
        JOIN notes n ON n.id = e.from_id
        WHERE e.to_id = ? AND n.deleted_at IS NULL
        ORDER BY e.created_at DESC
        """,
        (note_id,),
    ).fetchall()

    def _edge_dict(r):
        return {
            "id": r[0], "to_id" if "to_id" in r.keys() else "from_id": r[1] if "to_id" in r.keys() else r[1],
        }
    # 手动构建，兼容 Row 对象
    out_list = []
    for r in outgoing:
        out_list.append({
            "id": r["id"], "to_id": r["to_id"], "to_title": r["to_title"],
            "relation": r["relation"], "confidence": r["confidence"],
            "source": r["source"], "evidence": r["evidence"],
            "status": r["status"], "created_at": r["created_at"],
        })
    in_list = []
    for r in incoming:
        in_list.append({
            "id": r["id"], "from_id": r["from_id"], "from_title": r["from_title"],
            "relation": r["relation"], "confidence": r["confidence"],
            "source": r["source"], "evidence": r["evidence"],
            "status": r["status"], "created_at": r["created_at"],
        })

    return {"note_id": note_id, "outgoing": out_list, "incoming": in_list}


# ── GET /traces/recent ─────────────────────────────────────
@router.get("/traces/recent")
def list_traces(limit: int = 50, conn: sqlite3.Connection = Depends(get_conn)):
    """返回最近 trace 列表，聚合自 llm_calls 表。"""
    limit = min(limit, 100)
    rows = conn.execute(
        """
        SELECT trace_id,
               COUNT(*) as call_count,
               SUM(latency_ms) as total_latency_ms,
               SUM(cost_usd) as total_cost_usd,
               MIN(created_at) as started_at,
               MAX(created_at) as ended_at
        FROM llm_calls
        WHERE trace_id != ''
        GROUP BY trace_id
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    traces = []
    for r in rows:
        # 获取每个 trace 的 agent 列表和 session_id
        agents = conn.execute(
            "SELECT DISTINCT agent_id FROM llm_calls WHERE trace_id = ? AND agent_id != ''",
            (r["trace_id"],),
        ).fetchall()
        session_row = conn.execute(
            "SELECT DISTINCT session_id FROM llm_calls WHERE trace_id = ? LIMIT 1",
            (r["trace_id"],),
        ).fetchone()

        # 获取 verdict 信息（从工作记忆中推断）
        errors = conn.execute(
            "SELECT COUNT(*) FROM llm_errors WHERE llm_call_id IN "
            "(SELECT id FROM llm_calls WHERE trace_id = ?)",
            (r["trace_id"],),
        ).fetchone()[0]

        status = "ok"
        if errors > 0:
            status = "error"

        traces.append({
            "trace_id": r["trace_id"],
            "session_id": session_row["session_id"] if session_row else "",
            "agents": [a["agent_id"] for a in agents],
            "status": status,
            "call_count": r["call_count"],
            "latency_ms": r["total_latency_ms"],
            "cost_usd": round(r["total_cost_usd"], 6),
            "started_at": r["started_at"],
            "ended_at": r["ended_at"],
        })

    return {"traces": traces, "total": len(traces)}


# ── GET /traces/{trace_id} ──────────────────────────────────
@router.get("/traces/{trace_id}")
def get_trace_detail(trace_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """返回单条 trace 的完整 timeline。"""
    # LLM 调用记录
    call_rows = conn.execute(
        "SELECT id, session_id, agent_id, model, input_tokens, output_tokens, "
        "cost_usd, latency_ms, status, created_at "
        "FROM llm_calls WHERE trace_id = ? ORDER BY created_at ASC",
        (trace_id,),
    ).fetchall()
    calls = [dict(r) for r in call_rows]

    if not calls:
        raise HTTPException(404, f"trace {trace_id} not found")

    session_id = calls[0]["session_id"]

    # 用户输入（来自 messages 表）
    user_msg = conn.execute(
        "SELECT content, created_at FROM messages "
        "WHERE session_id = ? AND role = 'user' "
        "ORDER BY created_at ASC LIMIT 1",
        (session_id,),
    ).fetchone()

    # 错误信息
    call_ids = [c["id"] for c in calls]
    error_rows = []
    if call_ids:
        placeholders = ",".join("?" * len(call_ids))
        error_rows = conn.execute(
            f"SELECT id, llm_call_id, error_type, error_msg, created_at "
            f"FROM llm_errors WHERE llm_call_id IN ({placeholders}) "
            f"ORDER BY created_at ASC",
            call_ids,
        ).fetchall()

    # 按 agent 构建 timeline
    agent_timelines = []
    agent_order: list[str] = []
    agent_calls_map: dict[str, list] = {}
    for c in calls:
        aid = c["agent_id"] or "unknown"
        if aid not in agent_calls_map:
            agent_calls_map[aid] = []
            agent_order.append(aid)
        agent_calls_map[aid].append(c)

    for aid in agent_order:
        ac = agent_calls_map[aid]
        timeline = [{"type": "agent_start", "agent_id": aid, "timestamp": ac[0]["created_at"]}]
        for c in ac:
            timeline.append({
                "type": "llm_call",
                "agent_id": aid,
                "model": c["model"],
                "input_tokens": c["input_tokens"],
                "output_tokens": c["output_tokens"],
                "cost_usd": c["cost_usd"],
                "latency_ms": c["latency_ms"],
                "status": c["status"],
                "timestamp": c["created_at"],
            })
        timeline.append({"type": "agent_end", "agent_id": aid, "timestamp": ac[-1]["created_at"]})
        agent_timelines.append({"agent_id": aid, "call_count": len(ac), "timeline": timeline})

    # 组装 verdict
    has_errors = any(e is not None for e in error_rows)
    is_multi_agent = len(agent_order) > 1
    verdict = "natural_end"
    if has_errors:
        verdict = "error"
    elif len(calls) >= 10:
        verdict = "loop_detected"

    # 最后一个 agent 的最后一个 call status
    last_status = calls[-1]["status"]
    if last_status == "error":
        verdict = "error"

    return {
        "trace_id": trace_id,
        "session_id": session_id,
        "user_input": dict(user_msg) if user_msg else None,
        "agents": agent_timelines,
        "errors": [dict(e) for e in error_rows],
        "summary": {
            "total_tokens": sum(c["input_tokens"] + c["output_tokens"] for c in calls),
            "total_cost_usd": round(sum(c["cost_usd"] for c in calls), 6),
            "total_latency_ms": sum(c["latency_ms"] for c in calls),
            "call_count": len(calls),
            "agent_count": len(agent_order),
            "verdict": verdict,
            "started_at": calls[0]["created_at"],
            "ended_at": calls[-1]["created_at"],
        },
    }


# ── GET /suggestions ──────────────────────────────────────
@router.get("/suggestions")
def list_suggestions(status: str = "pending", conn: sqlite3.Connection = Depends(get_conn)):
    """返回待确认的建议列表（关系建议 + 标签建议）。"""
    rows = conn.execute(
        """
        SELECT ps.id, ps.from_id, ps.to_id, ps.relation, ps.confidence,
               ps.evidence, ps.suggestion_type, ps.status, ps.created_at,
               n1.title as from_title, n2.title as to_title
        FROM pending_suggestions ps
        LEFT JOIN notes n1 ON n1.id = ps.from_id
        LEFT JOIN notes n2 ON n2.id = ps.to_id
        WHERE ps.status = ?
        ORDER BY ps.created_at DESC
        LIMIT 50
        """,
        (status,),
    ).fetchall()
    return {
        "suggestions": [
            {
                "id": r["id"],
                "from_id": r["from_id"],
                "from_title": r["from_title"],
                "to_id": r["to_id"],
                "to_title": r["to_title"],
                "relation": r["relation"],
                "confidence": r["confidence"],
                "evidence": r["evidence"],
                "suggestion_type": r["suggestion_type"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    }


@router.post("/suggestions/{suggestion_id}/accept", status_code=200)
def accept_suggestion(suggestion_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """接受一条建议。"""
    row = conn.execute(
        "SELECT * FROM pending_suggestions WHERE id = ? AND status = 'pending'",
        (suggestion_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "suggestion not found or already processed")

    r = dict(row)
    if r["suggestion_type"] == "relation":
        edge_id = str(uuid.uuid4())
        conn.execute(
            """INSERT OR IGNORE INTO edges
               (id, from_id, to_id, relation, confidence, source, evidence, status)
               VALUES (?, ?, ?, ?, ?, 'llm', ?, 'confirmed')""",
            (edge_id, r["from_id"], r["to_id"], r["relation"], r["confidence"], r["evidence"]),
        )
        conn.execute(
            "UPDATE pending_suggestions SET status='accepted', decided_at=datetime('now','localtime') WHERE id=?",
            (suggestion_id,),
        )
        conn.commit()
        return {"status": "accepted", "suggestion_id": suggestion_id, "edge_id": edge_id}
    else:
        raise HTTPException(400, f"unsupported suggestion_type: {r['suggestion_type']}")


@router.post("/suggestions/{suggestion_id}/reject", status_code=200)
def reject_suggestion(suggestion_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """拒绝一条建议。"""
    row = conn.execute(
        "SELECT id FROM pending_suggestions WHERE id = ? AND status = 'pending'",
        (suggestion_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "suggestion not found or already processed")

    conn.execute(
        "UPDATE pending_suggestions SET status='rejected', decided_at=datetime('now','localtime') WHERE id=?",
        (suggestion_id,),
    )
    conn.commit()
    return {"status": "rejected", "suggestion_id": suggestion_id}


# ── GET /collisions ─────────────────────────────────────
@router.get("/collisions")
def list_collisions(limit: int = 20, conn: sqlite3.Connection = Depends(get_conn)):
    """返回已发现的 idea collisions。"""
    rows = conn.execute(
        """
        SELECT ic.id, ic.score, ic.connection, ic.angle, ic.is_read, ic.detected_by, ic.created_at,
               na.title as note_a_title, nb.title as note_b_title,
               ic.note_a_id, ic.note_b_id
        FROM idea_collisions ic
        JOIN notes na ON na.id = ic.note_a_id
        JOIN notes nb ON nb.id = ic.note_b_id
        ORDER BY ic.score DESC, ic.created_at DESC
        LIMIT ?
        """,
        (min(limit, 50),),
    ).fetchall()
    return {
        "collisions": [
            {
                "id": r["id"],
                "note_a": {"id": r["note_a_id"], "title": r["note_a_title"]},
                "note_b": {"id": r["note_b_id"], "title": r["note_b_title"]},
                "score": r["score"],
                "connection": r["connection"],
                "angle": r["angle"],
                "is_read": bool(r["is_read"]),
                "detected_by": r["detected_by"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    }


# ── GET /tags/aliases ───────────────────────────────────
@router.get("/tags/aliases")
def list_tag_aliases_rest(conn: sqlite3.Connection = Depends(get_conn)):
    """列出所有标签同义词映射。"""
    rows = conn.execute(
        "SELECT canonical, alias, created_at FROM tag_aliases ORDER BY canonical, alias"
    ).fetchall()
    return {"aliases": [{"canonical": r["canonical"], "alias": r["alias"], "created_at": r["created_at"]} for r in rows]}


# ── POST /tags/merge ────────────────────────────────────
class TagMergeBody(BaseModel):
    canonical: str
    aliases: list[str]


@router.post("/tags/merge", status_code=201)
def merge_tags_rest(body: TagMergeBody, conn: sqlite3.Connection = Depends(get_conn)):
    """合并同义标签到标准名称。"""
    merged = 0
    for alias in body.aliases:
        alias = alias.strip()
        if not alias or alias == body.canonical:
            continue
        tid = str(uuid.uuid4())
        try:
            conn.execute(
                "INSERT OR IGNORE INTO tag_aliases (id, canonical, alias) VALUES (?, ?, ?)",
                (tid, body.canonical, alias),
            )
            conn.commit()
            if conn.execute("SELECT id FROM tag_aliases WHERE id = ?", (tid,)).fetchone():
                merged += 1
        except Exception:
            pass
    return {"status": "ok", "canonical": body.canonical, "merged_count": merged}


# ── GET /notes/graph ─────────────────────────────────────
@router.get("/notes/graph")
def get_graph(center_id: str = "", depth: int = 2, conn: sqlite3.Connection = Depends(get_conn)):
    """返回笔记关系图谱（BFS）。center_id 为空时返回全图（上限 200 条笔记）。"""
    depth = min(max(depth, 1), 3)  # 1-3 跳

    if center_id:
        # BFS 遍历 edges
        visited: set[str] = set()
        frontier = {center_id}
        for _ in range(depth + 1):
            if not frontier:
                break
            visited.update(frontier)
            placeholders = ",".join("?" * len(frontier))
            new_ids = set()
            for fid in frontier:
                rows = conn.execute(
                    f"SELECT from_id, to_id FROM edges WHERE (from_id = ? OR to_id = ?) AND status != 'rejected'",
                    (fid, fid),
                ).fetchall()
                for r in rows:
                    nid = r["to_id"] if r["from_id"] == fid else r["from_id"]
                    if nid not in visited:
                        new_ids.add(nid)
            frontier = new_ids
        note_ids = visited
    else:
        # 全图（限制 200 条笔记）
        rows = conn.execute(
            "SELECT id FROM notes WHERE status='live' AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
        note_ids = {r["id"] for r in rows}

    if not note_ids:
        return {"nodes": [], "edges": []}

    # 获取笔记节点
    placeholders = ",".join("?" * len(note_ids))
    nodes = conn.execute(
        f"SELECT id, title, tags_json, status, created_at FROM notes WHERE id IN ({placeholders}) AND deleted_at IS NULL",
        list(note_ids),
    ).fetchall()

    # 获取节点之间的 edges
    edges = conn.execute(
        f"""SELECT id, from_id, to_id, relation, confidence, source, status
            FROM edges
            WHERE from_id IN ({placeholders}) AND to_id IN ({placeholders})
            AND status != 'rejected'""",
        list(note_ids) + list(note_ids),
    ).fetchall()

    # 统计每个节点的连接数
    conn_count: dict[str, int] = {}
    for e in edges:
        conn_count[e["from_id"]] = conn_count.get(e["from_id"], 0) + 1
        conn_count[e["to_id"]] = conn_count.get(e["to_id"], 0) + 1

    return {
        "nodes": [
            {
                "id": n["id"],
                "title": n["title"],
                "tags": json.loads(n["tags_json"] or "[]"),
                "status": n["status"],
                "connection_count": conn_count.get(n["id"], 0),
                "created_at": n["created_at"],
            }
            for n in nodes
        ],
        "edges": [
            {
                "id": e["id"],
                "from_id": e["from_id"],
                "to_id": e["to_id"],
                "relation": e["relation"],
                "confidence": e["confidence"],
                "source": e["source"],
                "status": e["status"],
            }
            for e in edges
        ],
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


