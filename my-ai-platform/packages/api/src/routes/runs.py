"""Read APIs for the hierarchical router runtime projection."""

import asyncio
import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.agent.run_events import list_run_events, verify_run_event_chain
from src.agent.router_graph_runtime import resume_graph_stream
from src.routes.dependencies import get_conn

router = APIRouter(prefix="/runs", tags=["runs"])


class ApprovalResolution(BaseModel):
    approved: bool
    comment: str = ""


def _run_projection(row: sqlite3.Row) -> dict:
    return {
        "run_id": row["id"],
        "session_id": row["session_id"],
        "status": row["status"],
        "current_node": row["current_node"],
        "prompt_version": row["prompt_version"],
        "final_verdict": row["final_verdict"],
        "final_output": row["final_output"],
        "error": json.loads(row["error_json"]),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


@router.get("/recent")
def recent_runs(
    limit: int = 30,
    conn: sqlite3.Connection = Depends(get_conn),
):
    rows = conn.execute(
        "SELECT * FROM agent_runs ORDER BY started_at DESC LIMIT ?",
        (min(max(limit, 1), 100),),
    ).fetchall()
    return [_run_projection(row) for row in rows]


@router.get("/{run_id}")
def get_run(run_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    projection = _run_projection(row)
    projection["event_chain_valid"] = verify_run_event_chain(conn, run_id)
    return projection


@router.get("/{run_id}/events")
def get_run_events(
    run_id: str,
    after_sequence: int = 0,
    conn: sqlite3.Connection = Depends(get_conn),
):
    exists = conn.execute("SELECT 1 FROM agent_runs WHERE id=?", (run_id,)).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail="run not found")
    return list_run_events(conn, run_id, after_sequence=after_sequence)


@router.get("/{run_id}/stream")
async def stream_run_events(run_id: str, after_sequence: int = 0):
    async def event_generator():
        from src.db.schema import get_conn as new_conn

        conn = new_conn()
        sequence = max(0, after_sequence)
        try:
            while True:
                run = conn.execute(
                    "SELECT status FROM agent_runs WHERE id=?", (run_id,)
                ).fetchone()
                if run is None:
                    yield {"event": "error", "data": "run not found"}
                    return
                events = list_run_events(conn, run_id, after_sequence=sequence)
                for event in events:
                    sequence = event["sequence"]
                    yield {
                        "id": str(sequence),
                        "event": event["type"],
                        "data": json.dumps(event, ensure_ascii=False),
                    }
                if run["status"] in {
                    "waiting_approval",
                    "completed",
                    "failed",
                    "cancelled",
                }:
                    return
                await asyncio.sleep(0.25)
        finally:
            conn.close()

    return EventSourceResponse(event_generator())


@router.post("/{run_id}/approvals/{approval_id}")
async def resolve_approval(
    run_id: str,
    approval_id: str,
    body: ApprovalResolution,
    conn: sqlite3.Connection = Depends(get_conn),
):
    approval = conn.execute(
        """SELECT status FROM approval_requests
           WHERE id=? AND run_id=?""",
        (approval_id, run_id),
    ).fetchone()
    if approval is None:
        raise HTTPException(status_code=404, detail="approval not found")
    if approval["status"] != "pending":
        raise HTTPException(status_code=409, detail="approval already resolved")

    async def event_generator():
        from src.db.schema import get_conn as new_conn

        stream_conn = new_conn()
        try:
            async for event in resume_graph_stream(
                run_id,
                {"approved": body.approved, "comment": body.comment},
                stream_conn,
            ):
                yield {
                    "event": event.get("type", "message"),
                    "data": json.dumps(event, ensure_ascii=False),
                }
        except (LookupError, ValueError) as exc:
            yield {"event": "error", "data": str(exc)}
        finally:
            stream_conn.close()

    return EventSourceResponse(event_generator())
