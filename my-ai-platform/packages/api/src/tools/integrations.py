"""Calendar, attachment, vision, and execution Agent tools."""

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

def build_integration_tools(conn: sqlite3.Connection) -> list:
    @tool
    async def get_today_events() -> str:
        """获取今日日程列表。需要 CalDAV 配置。返回 JSON：{ events: [{summary, start, end}] }"""
        from src.agent.calendar import get_today_events as _get
        return await _get()

    @tool
    async def get_week_events() -> str:
        """获取本周日程列表。需要 CalDAV 配置。返回 JSON：{ events: [{summary, start, end}] }"""
        from src.agent.calendar import get_week_events as _get_week
        return await _get_week()

    @tool
    async def create_calendar_event(title: str, date: str, time: str = "", duration_min: int = 60, notes: str = "") -> str:
        """创建日历事件。date 格式 YYYY-MM-DD，time 可选 HH:MM。duration_min 默认 60 分钟。"""
        from src.agent.calendar import create_event as _create
        return await _create(title, date, time, duration_min, notes)

    # ── Phase 7.4: Multimodal tools ──
    @tool
    def add_attachment(note_id: str, file_path: str) -> str:
        """
        给笔记添加附件（图片）。
        file_path 为本地文件路径（支持 png/jpg/gif/webp）。
        返回 JSON：{ status, path }
        """
        import os as _os
        import shutil as _shutil

        file_path = file_path.strip()
        if not _os.path.isfile(file_path):
            return json.dumps({"status": "error", "message": f"文件不存在: {file_path}"}, ensure_ascii=False)

        ext = file_path.rsplit(".", 1)[-1].lower()
        if ext not in ("png", "jpg", "jpeg", "gif", "webp"):
            return json.dumps({"status": "error", "message": "Only image files allowed (png/jpg/gif/webp)"}, ensure_ascii=False)

        # Determine data directory
        attach_dir = _os.path.join(_os.path.dirname(__file__), "..", "data", "attachments")
        _os.makedirs(attach_dir, exist_ok=True)

        fname = f"{note_id}_{uuid.uuid4().hex[:8]}.{ext}"
        dest = _os.path.join(attach_dir, fname)
        _shutil.copy2(file_path, dest)

        row = conn.execute("SELECT attachments_json FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not row:
            return json.dumps({"status": "error", "message": f"笔记 {note_id} 不存在"}, ensure_ascii=False)

        attachments = json.loads(row["attachments_json"] or "[]")
        attachments.append({"type": "image", "path": f"attachments/{fname}", "filename": _os.path.basename(file_path)})
        conn.execute("UPDATE notes SET attachments_json = ? WHERE id = ?", (json.dumps(attachments), note_id))
        conn.commit()
        return json.dumps({"status": "ok", "path": f"attachments/{fname}"}, ensure_ascii=False)

    @tool
    async def describe_images(note_id: str) -> str:
        """
        用 AI 描述笔记中图片的内容。需要多模态模型支持。
        返回 JSON：{ descriptions: [{path, description}] }
        """
        row = conn.execute("SELECT attachments_json FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not row:
            return json.dumps({"status": "error", "message": f"笔记 {note_id} 不存在"}, ensure_ascii=False)

        attachments = json.loads(row["attachments_json"] or "[]")
        images = [a for a in attachments if a.get("type") == "image"]
        if not images:
            return json.dumps({"descriptions": [], "message": "该笔记没有图片附件"}, ensure_ascii=False)

        # Check for GPT-4o or Gemini for vision
        import os as _os
        gpt_key = _os.environ.get("OPENAI_API_KEY", "")
        descriptions = []

        if gpt_key:
            try:
                import base64
                from openai import AsyncOpenAI

                client = AsyncOpenAI(api_key=gpt_key)
                for img in images[:3]:  # limit to 3 images
                    img_dir = _os.path.join(_os.path.dirname(__file__), "..", "data")
                    img_path = _os.path.join(img_dir, img["path"])
                    if not _os.path.isfile(img_path):
                        descriptions.append({"path": img["path"], "description": "[文件不存在]"})
                        continue

                    with open(img_path, "rb") as f:
                        img_data = base64.b64encode(f.read()).decode()

                    resp = await asyncio.wait_for(
                        client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[{"role": "user", "content": [
                                {"type": "text", "text": "用中文简短描述这张图片的内容（一句话）"},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_data}"}},
                            ]}],
                            max_tokens=100,
                        ),
                        timeout=TOOL_TIMEOUT,
                    )
                    descriptions.append({"path": img["path"], "description": resp.choices[0].message.content})
            except Exception as e:
                descriptions.append({"path": "auto", "description": f"AI 描述失败: {e}"})
        else:
            descriptions = [{"path": img["path"], "description": "[需要配置 OPENAI_API_KEY 以启用图片描述]"} for img in images[:3]]

        return json.dumps({"descriptions": descriptions}, ensure_ascii=False)

    # ── Phase 7.5: Code Execution ──
    @tool
    async def run_python(code: str) -> str:
        """
        在沙箱中运行 Python 代码片段，用于数据分析、计算验证等。
        超时 10s，禁用网络，仅可访问 /tmp。
        返回 stdout/stderr。
        需要 RUN_PYTHON_ENABLED=true 环境变量才会执行，否则返回 disabled。
        """
        import os as _os
        if _os.environ.get("RUN_PYTHON_ENABLED", "").lower() != "true":
            return json.dumps({"status": "disabled", "message": "run_python 未启用（设置 RUN_PYTHON_ENABLED=true）"}, ensure_ascii=False)

        # Check Docker availability first
        try:
            import subprocess as _sp
            docker_check = await asyncio.wait_for(
                asyncio.to_thread(lambda: _sp.run(["docker", "info"], capture_output=True, timeout=5)),
                timeout=8,
            )
            use_docker = docker_check.returncode == 0
        except Exception:
            use_docker = False

        if use_docker:
            # Docker sandbox: isolated, limited
            try:
                import subprocess as _sp
                import tempfile
                with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                    f.write(code)
                    tmp_path = f.name

                result = await asyncio.wait_for(
                    asyncio.to_thread(lambda: _sp.run(
                        [
                            "docker", "run", "--rm",
                            "--network=none",
                            "--memory=256m",
                            "--cpus=1",
                            "--timeout=10",
                            "-v", f"{tmp_path}:/code/script.py:ro",
                            "python:3.11-slim",
                            "python", "/code/script.py",
                        ],
                        capture_output=True, timeout=15,
                    )),
                    timeout=18,
                )
                _os.unlink(tmp_path)
                return json.dumps({
                    "stdout": result.stdout.decode("utf-8", errors="replace")[:4000],
                    "stderr": result.stderr.decode("utf-8", errors="replace")[:2000],
                    "returncode": result.returncode,
                }, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"status": "error", "message": f"Docker execution failed: {e}"}, ensure_ascii=False)
        else:
            # Subprocess fallback: restricted
            try:
                import subprocess as _sp
                result = await asyncio.wait_for(
                    asyncio.to_thread(lambda: _sp.run(
                        ["python", "-c", code],
                        capture_output=True, timeout=10,
                        text=True,
                    )),
                    timeout=12,
                )
                return json.dumps({
                    "stdout": result.stdout[:4000],
                    "stderr": result.stderr[:2000],
                    "returncode": result.returncode,
                }, ensure_ascii=False)
            except asyncio.TimeoutError:
                return json.dumps({"status": "error", "message": "代码执行超时（>10s）"}, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"status": "error", "message": f"Execution failed: {e}"}, ensure_ascii=False)

    return [get_today_events, get_week_events, create_calendar_event, add_attachment, describe_images, run_python]

