"""Chat streaming routes."""

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

def _build_sse_generator(user_input: str, session_id: str, prompt_version: str, trace_id: str):
    """构建 SSE 事件生成器，GET 和 POST 共用。"""
    async def event_generator():
        from src.db.schema import get_conn as new_conn
        stream_conn = new_conn()
        from src.agent.router import route_serial
        try:
            async for event in route_serial(user_input, session_id, conn=stream_conn, prompt_version=prompt_version, trace_id=trace_id):
                etype = event.get("type")

                if etype == "token":
                    yield {
                        "event": "token",
                        "data": json.dumps(
                            {"delta": event["delta"], "agentId": event["agentId"]},
                            ensure_ascii=False,
                        ),
                    }

                elif etype == "tool_start":
                    yield {
                        "event": "tool_start",
                        "data": json.dumps(
                            {
                                "name": event["name"],
                                "tool_call_id": event.get("tool_call_id", ""),
                                "input": event.get("input", {}),
                                "agentId": event["agentId"],
                            },
                            ensure_ascii=False,
                        ),
                    }

                elif etype == "tool_end":
                    yield {
                        "event": "tool_end",
                        "data": json.dumps(
                            {
                                "name": event["name"],
                                "tool_call_id": event.get("tool_call_id", ""),
                                "result": event.get("result", ""),
                                "agentId": event["agentId"],
                            },
                            ensure_ascii=False,
                        ),
                    }

                elif etype == "agent_switch":
                    yield {
                        "event": "agent_switch",
                        "data": json.dumps(
                            {
                                "agentId": event["agentId"],
                                "trace_id": event.get("trace_id", ""),
                            },
                            ensure_ascii=False,
                        ),
                    }

                elif etype == "warning":
                    yield {
                        "event": "warning",
                        "data": json.dumps(
                            {
                                "message": event.get("message", ""),
                                "agentId": event.get("agentId", ""),
                                "shadow": event.get("shadow", False),
                            },
                            ensure_ascii=False,
                        ),
                    }

                elif etype == "verdict":
                    yield {
                        "event": "verdict",
                        "data": json.dumps(
                            {
                                "reason": event.get("reason", ""),
                                "agentId": event.get("agentId", ""),
                            },
                            ensure_ascii=False,
                        ),
                    }

                elif etype == "done":
                    # 跳过 BaseAgent.astream 发出的 agent 级别 done（无 trace_id），
                    # 只透传 route_serial 的最终 done（携带完整 trace_id + phase_trace_ids）
                    if not event.get("trace_id"):
                        continue
                    done_data = {"session_id": session_id, "trace_id": event.get("trace_id", "")}
                    if event.get("phase_trace_ids"):
                        done_data["phase_trace_ids"] = event["phase_trace_ids"]
                    yield {"event": "done", "data": json.dumps(done_data)}

                elif etype == "error":
                    yield {"event": "error", "data": event.get("message", "unknown error")}

        except Exception as exc:
            yield {"event": "error", "data": str(exc)}
        finally:
            stream_conn.close()

    return event_generator()


class ChatStreamBody(BaseModel):
    input: str
    session_id: str = ""
    prompt_version: str = "v3"


# ── POST /chat/stream ─────────────────────────────────────
@router.post("/chat/stream")
async def chat_stream_post(body: ChatStreamBody):
    """POST 版本 — input 在 body 中，避免长文本导致 URL 截断 → 431。"""
    if not body.input:
        async def empty_gen():
            yield {"event": "error", "data": "input is required"}
        return EventSourceResponse(empty_gen())

    sid = body.session_id or str(uuid.uuid4())
    tid = str(uuid.uuid4())
    return EventSourceResponse(_build_sse_generator(body.input, sid, body.prompt_version, tid))


# ── GET /chat/stream（保留兼容）────────────────────────────
@router.get("/chat/stream")
async def chat_stream_get(
    input: str = "",
    session_id: str = "",
    prompt_version: str = "v3",
):
    """GET 版本 — 保留兼容，短文本仍可用。"""
    if not input:
        async def empty_gen():
            yield {"event": "error", "data": "input is required"}
        return EventSourceResponse(empty_gen())

    sid = session_id or str(uuid.uuid4())
    tid = str(uuid.uuid4())
    return EventSourceResponse(_build_sse_generator(input, sid, prompt_version, tid))
