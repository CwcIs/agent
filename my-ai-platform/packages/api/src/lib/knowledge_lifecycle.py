"""Candidate knowledge review and publication domain service."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid

from src.agent.governance import ensure_execution, mark_execution
from src.tools._shared import _create_wikilink_edges, _parse_wikilinks


def _approval_execution(
    conn: sqlite3.Connection,
    *,
    note_id: str,
    action: str,
    title: str,
    content: str,
) -> tuple[str, str]:
    content_hash = hashlib.sha256(f"{title}\n{content}".encode("utf-8")).hexdigest()
    _, idempotency_key, _ = ensure_execution(
        conn,
        proposal_id=f"knowledge:{note_id}:{content_hash}",
        action_type=action,
        actor_id="user",
        request_payload={
            "note_id": note_id,
            "title": title,
            "content_hash": content_hash,
            "approval_scope": "this_exact_candidate",
        },
    )
    return idempotency_key, content_hash


def publish_candidate(conn: sqlite3.Connection, note_id: str) -> dict:
    row = conn.execute(
        """SELECT id, title, content, knowledge_status, proposed_supersedes_id
           FROM notes WHERE id=? AND deleted_at IS NULL""",
        (note_id,),
    ).fetchone()
    if not row:
        raise LookupError("note not found")
    if row["knowledge_status"] == "canonical":
        return {"status": "canonical", "id": note_id, "already_published": True}
    if row["knowledge_status"] not in ("draft", "pending_review"):
        raise ValueError(f"cannot publish {row['knowledge_status']} knowledge")

    idempotency_key, content_hash = _approval_execution(
        conn,
        note_id=note_id,
        action="publish_knowledge",
        title=row["title"],
        content=row["content"],
    )
    mark_execution(conn, idempotency_key, "running")
    try:
        conn.execute(
            """UPDATE notes
               SET knowledge_status='canonical', reviewed_by='user',
                   reviewed_at=datetime('now','localtime'),
                   published_at=datetime('now','localtime'),
                   updated_at=datetime('now','localtime')
               WHERE id=?""",
            (note_id,),
        )
        edges = _create_wikilink_edges(
            conn,
            note_id,
            _parse_wikilinks(row["content"]),
        )

        old_id = row["proposed_supersedes_id"] or ""
        if old_id:
            old = conn.execute(
                """SELECT id FROM notes WHERE id=? AND knowledge_status='canonical'
                   AND deleted_at IS NULL""",
                (old_id,),
            ).fetchone()
            if old:
                conn.execute(
                    """UPDATE notes
                       SET status='superseded', knowledge_status='superseded',
                           superseded_by=?, updated_at=datetime('now','localtime')
                       WHERE id=?""",
                    (note_id, old_id),
                )
                edge_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT OR IGNORE INTO edges
                       (id, from_id, to_id, relation, confidence, source, evidence, status)
                       VALUES (?, ?, ?, 'evolved_from', 1.0, 'user_approved', ?,
                               'confirmed')""",
                    (edge_id, old_id, note_id, f"approved:{content_hash}"),
                )
                edges.append({"id": edge_id, "relation": "evolved_from"})
        conn.commit()
        mark_execution(
            conn,
            idempotency_key,
            "succeeded",
            result={"note_id": note_id, "edges_created": len(edges)},
        )
    except Exception as exc:
        conn.rollback()
        mark_execution(conn, idempotency_key, "failed", error_msg=str(exc))
        raise

    return {
        "status": "canonical",
        "id": note_id,
        "knowledge_status": "canonical",
        "edges_created": len(edges),
    }


def reject_candidate(conn: sqlite3.Connection, note_id: str) -> dict:
    row = conn.execute(
        """SELECT id, title, content, knowledge_status FROM notes
           WHERE id=? AND deleted_at IS NULL""",
        (note_id,),
    ).fetchone()
    if not row:
        raise LookupError("note not found")
    if row["knowledge_status"] not in ("draft", "pending_review"):
        raise ValueError(f"cannot reject {row['knowledge_status']} knowledge")

    idempotency_key, _ = _approval_execution(
        conn,
        note_id=note_id,
        action="reject_knowledge",
        title=row["title"],
        content=row["content"],
    )
    mark_execution(conn, idempotency_key, "running")
    conn.execute(
        """UPDATE notes
           SET knowledge_status='revoked', reviewed_by='user',
               reviewed_at=datetime('now','localtime'),
               updated_at=datetime('now','localtime')
           WHERE id=?""",
        (note_id,),
    )
    conn.commit()
    mark_execution(
        conn,
        idempotency_key,
        "succeeded",
        result={"note_id": note_id, "knowledge_status": "revoked"},
    )
    return {"status": "revoked", "id": note_id, "knowledge_status": "revoked"}
