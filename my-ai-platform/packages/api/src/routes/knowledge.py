"""Knowledge graph and suggestions routes."""

import json
import sqlite3
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.routes.dependencies import get_conn

router = APIRouter()

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
    if r["suggestion_type"] in ("relation", "contradiction"):
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
    elif r["suggestion_type"] == "tag_merge":
        canonical = r.get("relation", "")
        alias = r.get("evidence", "")
        if canonical and alias:
            tid = str(uuid.uuid4())
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO tag_aliases (id, canonical, alias) VALUES (?, ?, ?)",
                    (tid, canonical, alias),
                )
                conn.commit()
            except Exception:
                pass
        conn.execute(
            "UPDATE pending_suggestions SET status='accepted', decided_at=datetime('now','localtime') WHERE id=?",
            (suggestion_id,),
        )
        conn.commit()
        return {"status": "accepted", "suggestion_id": suggestion_id, "action": "merged_tags"}
    elif r["suggestion_type"] == "tag_suggest":
        conn.execute(
            "UPDATE pending_suggestions SET status='accepted', decided_at=datetime('now','localtime') WHERE id=?",
            (suggestion_id,),
        )
        conn.commit()
        return {"status": "accepted", "suggestion_id": suggestion_id, "action": "accepted_tag_suggestion"}
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

