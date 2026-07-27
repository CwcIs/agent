"""Search and import Agent tools."""

import asyncio
import json
import re
import sqlite3
import uuid
from typing import Optional

from langchain_core.tools import tool

from src.lib.trace import get_trace_context
from src.lib.embeddings import search_similar, upsert_embedding
from src.tools._shared import (
    TOOL_TIMEOUT,
    _background_embed,
    _create_wikilink_edges,
    _parse_wikilinks,
    _resolve_title_to_id,
    _task_done_callback,
)

def build_import_tools(conn: sqlite3.Connection) -> list:
    @tool
    async def web_search(query: str, k: int = 3) -> str:
        """
        搜索互联网获取最新信息。当笔记库和自己的知识不足以回答时使用。
        优先使用 Tavily Search API（专为 AI Agent 设计），不可用时回退 DuckDuckGo。
        返回 JSON：{ results: [{title, url, snippet, score?}], provider: 'tavily'|'duckduckgo' }
        """
        k = min(k, 5)

        # Try Tavily first
        try:
            import os as _os
            tavily_key = _os.environ.get("TAVILY_API_KEY", "")
            if tavily_key:
                import urllib.request, urllib.error
                req_body = json.dumps({"api_key": tavily_key, "query": query, "max_results": k, "search_depth": "basic"}).encode()
                req = urllib.request.Request(
                    "https://api.tavily.com/search",
                    data=req_body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                resp = await asyncio.wait_for(
                    asyncio.to_thread(lambda: urllib.request.urlopen(req, timeout=10).read()),
                    timeout=12,
                )
                data = json.loads(resp.decode())
                results = data.get("results", [])
                return json.dumps({
                    "results": [
                        {"title": r.get("title", ""), "url": r.get("url", ""),
                         "snippet": r.get("content", "")[:300], "score": r.get("score", 0)}
                        for r in results[:k]
                    ],
                    "provider": "tavily",
                }, ensure_ascii=False)
        except Exception:
            pass  # Fall through to DuckDuckGo

        # DuckDuckGo fallback
        try:
            from duckduckgo_search import DDGS
            results = await asyncio.wait_for(
                asyncio.to_thread(lambda: list(DDGS().text(query, max_results=k))),
                timeout=10,
            )
            return json.dumps({
                "results": [
                    {"title": r.get("title", ""), "url": r.get("href", ""),
                     "snippet": r.get("body", "")[:200]}
                    for r in results
                ],
                "provider": "duckduckgo",
            }, ensure_ascii=False)
        except asyncio.TimeoutError:
            return json.dumps({"status": "error", "message": "Web 搜索超时，请稍后重试"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Web 搜索失败: {e}"}, ensure_ascii=False)

    @tool
    async def import_file(file_path: str, tags: str = "") -> str:
        """
        将本地文件导入为笔记（支持 .md / .pdf / .txt）。
        file_path 为文件绝对路径。tags 用逗号分隔。
        返回 JSON：{ status, note_id, title, word_count, source_file }
        """
        import hashlib
        import os as _os

        file_path = file_path.strip()
        if not _os.path.isfile(file_path):
            return json.dumps({"status": "error", "message": f"文件不存在: {file_path}"}, ensure_ascii=False)

        filename = _os.path.basename(file_path)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        file_size = _os.path.getsize(file_path)
        if file_size > 10 * 1024 * 1024:
            return json.dumps({"status": "error", "message": "文件过大（>10MB）"}, ensure_ascii=False)

        try:
            with open(file_path, "rb") as f:
                raw = f.read()
        except Exception as e:
            return json.dumps({"status": "error", "message": f"读取文件失败: {e}"}, ensure_ascii=False)

        title = filename
        content = ""
        if ext in ("md", "markdown"):
            content = raw.decode("utf-8", errors="replace")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    for line in parts[1].split("\n"):
                        if line.startswith("title:"):
                            title = line.split("title:", 1)[1].strip().strip("\"'")
                    content = parts[2].strip()
        elif ext == "pdf":
            try:
                from PyPDF2 import PdfReader
                from io import BytesIO
                reader = PdfReader(BytesIO(raw))
                content = "\n".join(page.extract_text() or "" for page in reader.pages)[:50000]
            except Exception:
                content = "[PDF 解析失败]"
        elif ext == "txt":
            content = raw.decode("utf-8", errors="replace")
        else:
            content = raw.decode("utf-8", errors="replace")

        note_id = str(uuid.uuid4())
        tags_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        word_count = len(content.split())

        conn.execute(
            "INSERT INTO notes (id, title, content, tags_json, source_file, source_type, word_count, knowledge_status, origin_session_id) "
            "VALUES (?, ?, ?, ?, ?, 'file', ?, 'pending_review', ?)",
            (
                note_id,
                title[:200],
                content,
                json.dumps(tags_list, ensure_ascii=False),
                filename,
                word_count,
                get_trace_context().session_id,
            ),
        )
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        try:
            conn.execute(
                "INSERT INTO source_trace (id, note_id, source_type, source_file, content_hash, fetch_status) "
                "VALUES (?, ?, 'file', ?, ?, 'ok')",
                (str(uuid.uuid4()), note_id, filename, content_hash),
            )
        except Exception:
            pass
        conn.commit()

        # 后台 embedding
        task = asyncio.create_task(_background_embed(conn, note_id, title, content))
        _background_tasks.add(task)
        task.add_done_callback(_task_done_callback)

        return json.dumps({
            "status": "pending_review", "note_id": note_id, "title": title[:200],
            "knowledge_status": "pending_review",
            "word_count": word_count, "source_file": filename,
        }, ensure_ascii=False)

    @tool
    async def import_webpage(url: str, tags: str = "") -> str:
        """
        将网页 URL 导入为笔记。用户说"把这篇保存下来"、"导入这个链接"时调用。
        tags 用逗号分隔，例如 'AI,研究'。
        自动提取正文、标题，生成内容哈希去重。
        返回 JSON：{ status, note_id, title, word_count }
        """
        import hashlib
        from urllib.parse import urlparse
        import ipaddress
        import socket

        url = url.strip()
        if not url.startswith(("http://", "https://")):
            return json.dumps({"status": "error", "message": "URL must start with http:// or https://"}, ensure_ascii=False)

        # SSRF 防护
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        try:
            resolved = socket.getaddrinfo(hostname, None)
            for _, _, _, _, sockaddr in resolved:
                ip = sockaddr[0]
                try:
                    addr = ipaddress.ip_address(ip)
                    if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_multicast:
                        return json.dumps({"status": "error", "message": f"Blocked internal IP: {ip}"}, ensure_ascii=False)
                except ValueError:
                    pass
        except Exception as e:
            return json.dumps({"status": "error", "message": f"DNS resolution failed: {e}"}, ensure_ascii=False)

        try:
            import trafilatura
            downloaded = await asyncio.wait_for(
                asyncio.to_thread(trafilatura.fetch_url, url),
                timeout=15,
            )
            if not downloaded:
                return json.dumps({"status": "error", "message": "Failed to fetch URL"}, ensure_ascii=False)

            extracted = trafilatura.extract(downloaded, include_comments=False, include_tables=False,
                                             favor_precision=True, output_format="markdown")
            title = trafilatura.extract(downloaded, include_comments=False, output_format="title") or url
            content = extracted or "[无法提取正文]"
        except asyncio.TimeoutError:
            return json.dumps({"status": "error", "message": "Fetch timeout (>15s)"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Extraction failed: {e}"}, ensure_ascii=False)

        if len(content) > 5 * 1024 * 1024:
            return json.dumps({"status": "error", "message": "Content too large (>5MB)"}, ensure_ascii=False)

        note_id = str(uuid.uuid4())
        tags_list = [t.strip() for t in (tags or "").split(",") if t.strip()]

        conn.execute(
            "INSERT INTO notes (id, title, content, tags_json, source_url, source_type, word_count, knowledge_status, origin_session_id) "
            "VALUES (?, ?, ?, ?, ?, 'web', ?, 'pending_review', ?)",
            (
                note_id,
                title[:200],
                content,
                json.dumps(tags_list, ensure_ascii=False),
                url,
                len(content.split()),
                get_trace_context().session_id,
            ),
        )
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        conn.execute(
            "INSERT INTO source_trace (id, note_id, source_type, source_url, content_hash, fetch_status) "
            "VALUES (?, ?, 'web', ?, ?, 'ok')",
            (str(uuid.uuid4()), note_id, url, content_hash),
        )
        conn.commit()

        # 后台 embedding
        task = asyncio.create_task(_background_embed(conn, note_id, title, content))
        _background_tasks.add(task)
        task.add_done_callback(_task_done_callback)

        return json.dumps({
            "status": "pending_review", "note_id": note_id, "title": title[:200],
            "knowledge_status": "pending_review",
            "word_count": len(content.split()), "source_url": url,
        }, ensure_ascii=False)

    return [web_search, import_webpage, import_file]
