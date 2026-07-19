"""Note CRUD routes."""

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

