"""Dynamic custom Agent tools."""

import asyncio
import json
import re
import sqlite3
import uuid
from typing import Optional

from langchain_core.tools import tool

from src.lib.embeddings import search_similar, upsert_embedding
from src.tools._shared import (
    TOOL_TIMEOUT,
    _background_embed,
    _create_wikilink_edges,
    _parse_wikilinks,
    _resolve_title_to_id,
    _task_done_callback,
)

def build_custom_tools(conn: sqlite3.Connection) -> list:
    # ── Phase 7.3: Dynamic custom tools from DB ──
    custom = []
    try:
        ct_rows = conn.execute(
            "SELECT name, description, endpoint, method, params_json, output_template FROM custom_tools WHERE enabled = 1"
        ).fetchall()
        for ct in ct_rows:
            _name = ct["name"]
            _desc = ct["description"]
            _endpoint = ct["endpoint"]
            _method = ct["method"].upper()
            _params = json.loads(ct["params_json"] or "{}")
            _template = ct["output_template"]

            @tool
            async def _dynamic_tool(input_str: str = "", _n=_name, _d=_desc, _ep=_endpoint, _m=_method, _p=_params, _t=_template) -> str:
                """Dynamically loaded custom tool. See description for details."""
                try:
                    import urllib.request, urllib.error
                    if _m == "GET":
                        qs = "&".join(f"{k}={v}" for k, v in _p.items()) if _p else ""
                        url = f"{_ep}?{qs}" if qs else _ep
                        req = urllib.request.Request(url, method="GET")
                    else:
                        data = json.dumps(_p).encode() if _p else b"{}"
                        req = urllib.request.Request(_ep, data=data, method="POST",
                                                     headers={"Content-Type": "application/json"})
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(lambda: urllib.request.urlopen(req, timeout=10).read()),
                        timeout=12,
                    )
                    raw = resp.decode("utf-8", errors="replace")[:2000]
                    result = _t.replace("{{response}}", raw)
                    return result
                except Exception as e:
                    return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

            _dynamic_tool.name = _name
            _dynamic_tool.description = _desc
            custom.append(_dynamic_tool)
    except Exception:
        pass

    return custom

