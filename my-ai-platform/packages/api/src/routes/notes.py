"""Note CRUD and candidate knowledge publication routes."""

import asyncio
import json
import sqlite3
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.lib.knowledge_lifecycle import publish_candidate, reject_candidate
from src.routes.dependencies import get_conn
from src.tools._shared import (
    _background_embed,
    _create_wikilink_edges,
    _parse_wikilinks,
    _task_done_callback,
)

router = APIRouter()


def _serialize_note(row: sqlite3.Row) -> dict:
    note = dict(row)
    note["tags"] = json.loads(note.pop("tags_json", "[]"))
    return note


@router.get("/notes")
def list_notes(
    knowledge_status: str | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
):
    allowed_statuses = {
        "draft", "pending_review", "canonical", "superseded", "revoked", "expired"
    }
    if knowledge_status is not None and knowledge_status not in allowed_statuses:
        raise HTTPException(400, "invalid knowledge_status")
    sql = """SELECT id, title, content, summary, tags_json, status, knowledge_status,
                    proposed_supersedes_id, origin_session_id, source_type, created_at
             FROM notes
             WHERE deleted_at IS NULL"""
    params: tuple[str, ...] = ()
    if knowledge_status is not None:
        sql += " AND knowledge_status = ?"
        params = (knowledge_status,)
    sql += " ORDER BY created_at DESC LIMIT 100"
    rows = conn.execute(sql, params).fetchall()
    return {"notes": [_serialize_note(row) for row in rows]}


class NoteIn(BaseModel):
    title: str
    content: str
    tags: str = ""


@router.post("/notes", status_code=201)
async def create_note(body: NoteIn, conn: sqlite3.Connection = Depends(get_conn)):
    """A direct user write is canonical because the user supplied the content."""
    note_id = str(uuid.uuid4())
    tags = [tag.strip() for tag in body.tags.split(",") if tag.strip()]
    conn.execute(
        """INSERT INTO notes
           (id, title, content, tags_json, source_type, knowledge_status, published_at)
           VALUES (?, ?, ?, ?, 'user', 'canonical', datetime('now','localtime'))""",
        (note_id, body.title, body.content, json.dumps(tags, ensure_ascii=False)),
    )
    conn.commit()
    _create_wikilink_edges(conn, note_id, _parse_wikilinks(body.content))
    task = asyncio.create_task(_background_embed(conn, note_id, body.title, body.content))
    task.add_done_callback(_task_done_callback)
    return {
        "status": "ok",
        "id": note_id,
        "title": body.title,
        "knowledge_status": "canonical",
    }


@router.delete("/notes/{note_id}", status_code=200)
def delete_note(note_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = conn.execute(
        "SELECT id FROM notes WHERE id = ? AND deleted_at IS NULL",
        (note_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "note not found")
    conn.execute(
        "UPDATE notes SET deleted_at=datetime('now','localtime') WHERE id=?",
        (note_id,),
    )
    conn.commit()
    return {"status": "deleted", "id": note_id}


class NotePatch(BaseModel):
    title: str | None = None
    content: str | None = None
    status: str | None = None


@router.patch("/notes/{note_id}", status_code=200)
def patch_note(
    note_id: str,
    body: NotePatch,
    conn: sqlite3.Connection = Depends(get_conn),
):
    row = conn.execute(
        "SELECT id, title, content, status FROM notes WHERE id=? AND deleted_at IS NULL",
        (note_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "note not found")
    if body.status is not None and body.status not in ("archived", "live"):
        raise HTTPException(400, "status must be archived or live")

    title = body.title if body.title is not None else row["title"]
    content = body.content if body.content is not None else row["content"]
    status = body.status if body.status is not None else row["status"]
    conn.execute(
        """UPDATE notes
           SET title=?, content=?, status=?, updated_at=datetime('now','localtime')
           WHERE id=?""",
        (title, content, status, note_id),
    )
    conn.commit()
    return {
        "status": status,
        "id": note_id,
        "title": title,
        "content": content,
    }


@router.post("/notes/{note_id}/publish")
def publish_note_candidate(
    note_id: str,
    conn: sqlite3.Connection = Depends(get_conn),
):
    try:
        return publish_candidate(conn, note_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, "failed to publish candidate") from exc


@router.post("/notes/{note_id}/reject")
def reject_note_candidate(
    note_id: str,
    conn: sqlite3.Connection = Depends(get_conn),
):
    try:
        return reject_candidate(conn, note_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
