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
def get_graph(
    center_id: str = "",
    depth: int = 2,
    include_suggested: bool = False,
    relation: str = "",
    min_confidence: float = 0.0,
    limit: int = 200,
    conn: sqlite3.Connection = Depends(get_conn),
):
    """返回笔记关系图谱（BFS）。center_id 为空时返回全图（默认上限 200 条笔记）。"""
    depth = min(max(depth, 1), 3)  # 1-3 跳
    limit = min(max(limit, 20), 500)
    min_confidence = min(max(min_confidence, 0.0), 1.0)
    allowed_relations = {"wikilink", "evolved_from", "supersedes", "contradicts", "similar", "related"}
    relation_filters = {
        r.strip()
        for r in relation.split(",")
        if r.strip() in allowed_relations
    }

    def _edge_where(prefix: str = "") -> tuple[str, list]:
        clauses = [f"{prefix}status != 'rejected'", f"{prefix}confidence >= ?"]
        params: list = [min_confidence]
        if not include_suggested:
            clauses.append(f"{prefix}status = 'confirmed'")
        if relation_filters:
            placeholders = ",".join("?" * len(relation_filters))
            clauses.append(f"{prefix}relation IN ({placeholders})")
            params.extend(sorted(relation_filters))
        return " AND ".join(clauses), params

    if center_id:
        # BFS 遍历 edges
        visited: set[str] = set()
        frontier = {center_id}
        edge_where, edge_params = _edge_where()
        for _ in range(depth + 1):
            if not frontier:
                break
            visited.update(frontier)
            new_ids = set()
            for fid in frontier:
                rows = conn.execute(
                    f"SELECT from_id, to_id FROM edges WHERE (from_id = ? OR to_id = ?) AND {edge_where}",
                    [fid, fid, *edge_params],
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
            "SELECT id FROM notes WHERE status='live' "
            "AND knowledge_status='canonical' AND deleted_at IS NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
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
    edge_where, edge_params = _edge_where()
    edges = conn.execute(
        f"""SELECT id, from_id, to_id, relation, confidence, source, status, evidence, created_at
            FROM edges
            WHERE from_id IN ({placeholders}) AND to_id IN ({placeholders})
            AND {edge_where}""",
        [*list(note_ids), *list(note_ids), *edge_params],
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
                "evidence": e["evidence"],
                "created_at": e["created_at"],
            }
            for e in edges
        ],
        "meta": {
            "center_id": center_id,
            "depth": depth if center_id else None,
            "include_suggested": include_suggested,
            "min_confidence": min_confidence,
            "relations": sorted(relation_filters),
            "limit": limit,
        },
    }
