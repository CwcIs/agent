"""Extensions, attachments, and exports routes."""

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

class CustomToolIn(BaseModel):
    name: str
    description: str = ""
    endpoint: str
    method: str = "GET"
    params_json: str = "{}"
    headers_json: str = "{}"
    output_template: str = "{{response}}"
    enabled: bool = True


@router.get("/custom-tools")
def list_custom_tools(conn: sqlite3.Connection = Depends(get_conn)):
    rows = conn.execute("SELECT * FROM custom_tools ORDER BY created_at DESC").fetchall()
    return {"tools": [dict(r) for r in rows]}


@router.post("/custom-tools", status_code=201)
def create_custom_tool(body: CustomToolIn, conn: sqlite3.Connection = Depends(get_conn)):
    tid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO custom_tools (id, name, description, endpoint, method, params_json, headers_json, output_template, enabled)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (tid, body.name, body.description, body.endpoint, body.method,
         body.params_json, body.headers_json, body.output_template, int(body.enabled)),
    )
    conn.commit()
    return {"status": "ok", "id": tid}


@router.delete("/custom-tools/{tool_id}", status_code=200)
def delete_custom_tool(tool_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    conn.execute("DELETE FROM custom_tools WHERE id = ?", (tool_id,))
    conn.commit()
    return {"status": "deleted", "id": tool_id}


# ── File Upload (multimodal) ─────────────────────────────
@router.post("/notes/{note_id}/attachments", status_code=201)
async def upload_attachment(note_id: str, file: UploadFile = File(...),
                            conn: sqlite3.Connection = Depends(get_conn)):
    """给笔记添加图片附件，存储到 data/attachments/。"""
    import os as _os
    attach_dir = _os.path.join(_os.path.dirname(__file__), "..", "data", "attachments")
    _os.makedirs(attach_dir, exist_ok=True)

    ext = (file.filename or "img.png").rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "gif", "webp"):
        raise HTTPException(400, "Only image files allowed (png/jpg/gif/webp)")

    fname = f"{note_id}_{uuid.uuid4().hex[:8]}.{ext}"
    fpath = _os.path.join(attach_dir, fname)
    with open(fpath, "wb") as f:
        f.write(await file.read())

    row = conn.execute("SELECT attachments_json FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not row:
        raise HTTPException(404, "note not found")
    attachments = json.loads(row["attachments_json"] or "[]")
    attachments.append({"type": "image", "path": f"attachments/{fname}", "filename": file.filename})
    conn.execute("UPDATE notes SET attachments_json = ? WHERE id = ?", (json.dumps(attachments), note_id))
    conn.commit()
    return {"status": "ok", "path": f"attachments/{fname}"}


# ── Notes Export ─────────────────────────────────────────
@router.get("/notes/export")
def export_notes(fmt: str = "markdown", conn: sqlite3.Connection = Depends(get_conn)):
    """导出所有笔记为 Markdown (ZIP) 或 JSON。"""
    import zipfile
    import io

    rows = conn.execute(
        "SELECT id, title, content, tags_json, status, source_url, source_type, word_count, created_at "
        "FROM notes WHERE deleted_at IS NULL ORDER BY created_at DESC"
    ).fetchall()

    if fmt == "json":
        notes = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d["tags_json"] or "[]")
            del d["tags_json"]
            notes.append(d)
        from fastapi.responses import JSONResponse
        return JSONResponse({"notes": notes, "exported_at": date.today().isoformat()})

    # Markdown ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in rows:
            d = dict(r)
            tags = json.loads(d["tags_json"] or "[]")
            frontmatter = f"---\ntitle: {d['title']}\ntags: {', '.join(tags)}\nstatus: {d['status']}\n"
            if d["source_url"]:
                frontmatter += f"source_url: {d['source_url']}\n"
            frontmatter += f"created_at: {d['created_at']}\n---\n\n"
            safe_title = "".join(c for c in d["title"][:40] if c.isalnum() or c in " _-").strip() or "untitled"
            zf.writestr(f"{safe_title}.md", frontmatter + d["content"])

    buf.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=notes-export-{date.today().isoformat()}.zip"},
    )

