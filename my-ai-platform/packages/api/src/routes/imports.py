"""Knowledge import and lineage routes."""

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

class WebImportBody(BaseModel):
    url: str
    tags: str = ""
    auto_tags: bool = True


@router.post("/notes/import/web", status_code=201)
async def import_webpage(body: WebImportBody, conn: sqlite3.Connection = Depends(get_conn)):
    """导入网页 URL 为笔记。自动提取正文，可选 AI 标签。"""
    import hashlib
    from urllib.parse import urlparse
    import ipaddress

    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL must start with http:// or https://")

    # ── SSRF 防护 ──
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    # DNS rebinding: resolve hostname → check not internal IP
    import socket
    try:
        resolved = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in resolved:
            ip = sockaddr[0]
            try:
                addr = ipaddress.ip_address(ip)
                if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_multicast:
                    raise HTTPException(400, f"Blocked internal IP: {ip}")
                if ip == "0.0.0.0" or ip == "::":
                    raise HTTPException(400, f"Blocked null IP: {ip}")
            except ValueError:
                pass
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"DNS resolution failed: {e}")

    # 抓取
    try:
        import trafilatura
        import asyncio
        downloaded = await asyncio.wait_for(
            asyncio.to_thread(trafilatura.fetch_url, url),
            timeout=15,
        )
        if not downloaded:
            raise HTTPException(502, "Failed to fetch URL")
        extracted = trafilatura.extract(downloaded, include_comments=False, include_tables=False,
                                         favor_precision=True, output_format="markdown")
        title = trafilatura.extract(downloaded, include_comments=False, output_format="title") or url
        content = extracted or f"[无法提取正文内容]\n{trafilatura.extract(downloaded, include_comments=False, output_format='txt') or ''}"
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        raise HTTPException(504, "Fetch timeout (>15s)")
    except Exception as e:
        raise HTTPException(502, f"Extraction failed: {e}")

    # 内容大小限制 5MB
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Content too large (>5MB)")

    # 去重: content_hash
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    dup = conn.execute(
        "SELECT s.note_id FROM source_trace s WHERE s.content_hash = ? AND s.source_url = ?",
        (content_hash, url),
    ).fetchone()
    if dup:
        return {"status": "duplicate", "note_id": dup["note_id"], "message": "同一来源已导入过"}

    note_id = str(uuid.uuid4())
    tags_list = [t.strip() for t in (body.tags or "").split(",") if t.strip()]

    conn.execute(
        "INSERT INTO notes (id, title, content, tags_json, source_url, source_type, word_count) "
        "VALUES (?, ?, ?, ?, ?, 'web', ?)",
        (note_id, title[:200], content, json.dumps(tags_list, ensure_ascii=False), url, len(content.split())),
    )

    conn.execute(
        "INSERT INTO source_trace (id, note_id, source_type, source_url, content_hash, fetch_status) "
        "VALUES (?, ?, 'web', ?, ?, 'ok')",
        (str(uuid.uuid4()), note_id, url, content_hash),
    )
    conn.commit()

    # 后台 embedding
    from src.tools import _background_embed
    import asyncio as aio
    aio.create_task(_background_embed(conn, note_id, title, content))

    return {"status": "ok", "note_id": note_id, "title": title[:200],
            "word_count": len(content.split()), "source_url": url}


# ── POST /notes/import/file ──────────────────────────────
from fastapi import UploadFile, File, Form


@router.post("/notes/import/file", status_code=201)
async def import_file(
    file: UploadFile = File(...),
    tags: str = Form(""),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """导入文件为笔记（支持 .md / .pdf / .txt）。"""
    import hashlib

    filename = file.filename or "untitled"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # 读取文件内容
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (>10MB)")

    title = filename
    content = ""

    if ext == "md" or ext == "markdown":
        content = raw.decode("utf-8", errors="replace")
        # 提取 frontmatter title
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                for line in frontmatter.split("\n"):
                    if line.startswith("title:"):
                        title = line.split("title:", 1)[1].strip().strip("\"'")
                content = parts[2].strip()
        source_type = "file"
    elif ext == "pdf":
        try:
            from PyPDF2 import PdfReader
            from io import BytesIO
            reader = PdfReader(BytesIO(raw))
            content = "\n".join(page.extract_text() or "" for page in reader.pages)[:50000]
        except Exception:
            content = "[PDF 解析失败]"
        source_type = "file"
    elif ext == "txt":
        content = raw.decode("utf-8", errors="replace")
        source_type = "file"
    else:
        # 尝试作为纯文本
        content = raw.decode("utf-8", errors="replace")
        source_type = "file"

    content_hash = hashlib.sha256(content.encode()).hexdigest()
    dup = conn.execute(
        "SELECT s.note_id FROM source_trace s WHERE s.content_hash = ? AND s.source_file = ?",
        (content_hash, filename),
    ).fetchone()
    if dup:
        return {"status": "duplicate", "note_id": dup["note_id"], "message": "同一文件已导入过"}

    note_id = str(uuid.uuid4())
    tags_list = [t.strip() for t in (tags or "").split(",") if t.strip()]

    conn.execute(
        "INSERT INTO notes (id, title, content, tags_json, source_file, source_type, word_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (note_id, title[:200], content, json.dumps(tags_list, ensure_ascii=False), filename,
         source_type, len(content.split())),
    )
    conn.execute(
        "INSERT INTO source_trace (id, note_id, source_type, source_file, content_hash, fetch_status) "
        "VALUES (?, ?, ?, ?, ?, 'ok')",
        (str(uuid.uuid4()), note_id, source_type, filename, content_hash),
    )
    conn.commit()

    # 后台 embedding
    from src.tools import _background_embed
    import asyncio as aio
    aio.create_task(_background_embed(conn, note_id, title, content))

    return {"status": "ok", "note_id": note_id, "title": title[:200],
            "word_count": len(content.split()), "source_file": filename}


# ── GET /notes/{id}/trace ────────────────────────────────
@router.get("/notes/{note_id}/trace")
def trace_note_lineage(note_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """返回笔记的知识溯源链：ancestors（回溯到最早来源）+ descendants（正向衍生）。"""
    note = conn.execute(
        "SELECT id, title, source_url, source_file, source_type FROM notes WHERE id = ? AND deleted_at IS NULL",
        (note_id,),
    ).fetchone()
    if not note:
        raise HTTPException(404, "note not found")

    # 向上追溯（evolved_from + wikilink）
    ancestors: list[dict] = []
    visited = {note_id}
    frontier = [note_id]
    for _ in range(10):  # 最多 10 层
        if not frontier:
            break
        placeholders = ",".join("?" * len(frontier))
        rows = conn.execute(
            f"""SELECT DISTINCT e.from_id, n.title, e.relation, e.confidence, e.source
                FROM edges e JOIN notes n ON n.id = e.from_id
                WHERE e.to_id IN ({placeholders})
                  AND e.relation IN ('evolved_from','wikilink','supersedes')
                  AND e.from_id NOT IN ({",".join("?" * len(visited))})
                  AND n.deleted_at IS NULL""",
            frontier + list(visited),
        ).fetchall()
        frontier = []
        for r in rows:
            if r["from_id"] not in visited:
                ancestors.insert(0, {"id": r["from_id"], "title": r["title"],
                                      "relation": r["relation"], "confidence": r["confidence"],
                                      "source": r["source"]})
                visited.add(r["from_id"])
                frontier.append(r["from_id"])

    # 向下追溯
    descendants: list[dict] = []
    visited2 = {note_id}
    frontier2 = [note_id]
    for _ in range(10):
        if not frontier2:
            break
        placeholders = ",".join("?" * len(frontier2))
        rows = conn.execute(
            f"""SELECT DISTINCT e.to_id, n.title, e.relation, e.confidence, e.source
                FROM edges e JOIN notes n ON n.id = e.to_id
                WHERE e.from_id IN ({placeholders})
                  AND e.to_id NOT IN ({",".join("?" * len(visited2))})
                  AND n.deleted_at IS NULL""",
            frontier2 + list(visited2),
        ).fetchall()
        frontier2 = []
        for r in rows:
            if r["to_id"] not in visited2:
                descendants.append({"id": r["to_id"], "title": r["title"],
                                     "relation": r["relation"], "confidence": r["confidence"],
                                     "source": r["source"]})
                visited2.add(r["to_id"])
                frontier2.append(r["to_id"])

    return {
        "note_id": note_id,
        "title": note["title"],
        "source": {"url": note["source_url"], "file": note["source_file"], "type": note["source_type"]},
        "ancestors": ancestors,
        "descendants": descendants,
    }


# ── GET /notes/source/{source_url_or_file} ───────────────
@router.get("/notes/source-group")
def source_group(source_url: str = "", source_file: str = "", conn: sqlite3.Connection = Depends(get_conn)):
    """获取来自同一来源的所有笔记。"""
    if source_url:
        rows = conn.execute(
            "SELECT id, title, source_type, word_count, created_at FROM notes "
            "WHERE source_url = ? AND deleted_at IS NULL ORDER BY created_at",
            (source_url,),
        ).fetchall()
    elif source_file:
        rows = conn.execute(
            "SELECT id, title, source_type, word_count, created_at FROM notes "
            "WHERE source_file = ? AND deleted_at IS NULL ORDER BY created_at",
            (source_file,),
        ).fetchall()
    else:
        raise HTTPException(400, "source_url or source_file required")

    return {
        "notes": [{"id": r["id"], "title": r["title"], "source_type": r["source_type"],
                    "word_count": r["word_count"], "created_at": r["created_at"]} for r in rows],
        "total": len(rows),
    }

