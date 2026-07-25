"""Trace ledger query endpoints."""

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from src.lib.trace import assess_trace, decode_event, elapsed_ms
from src.routes.dependencies import get_conn

router = APIRouter()


def _load_events(conn: sqlite3.Connection, trace_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM trace_events WHERE trace_id = ? ORDER BY sequence",
        (trace_id,),
    ).fetchall()


def _resolve_root_trace(conn: sqlite3.Connection, requested_id: str) -> tuple[str, str]:
    row = conn.execute(
        "SELECT trace_id, phase_trace_id FROM trace_events "
        "WHERE trace_id = ? OR phase_trace_id = ? "
        "ORDER BY CASE WHEN trace_id = ? THEN 0 ELSE 1 END, sequence LIMIT 1",
        (requested_id, requested_id, requested_id),
    ).fetchone()
    if not row:
        return "", ""
    phase_id = requested_id if requested_id != row["trace_id"] else ""
    return row["trace_id"], phase_id


def _load_llm_calls(
    conn: sqlite3.Connection,
    phase_ids: list[str],
) -> list[dict]:
    if not phase_ids:
        return []
    placeholders = ",".join("?" * len(phase_ids))
    rows = conn.execute(
        f"SELECT id, session_id, agent_id, model, input_tokens, output_tokens, "
        f"cost_usd, latency_ms, status, trace_id, created_at "
        f"FROM llm_calls WHERE trace_id IN ({placeholders}) ORDER BY created_at, id",
        phase_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def _legacy_trace_detail(trace_id: str, conn: sqlite3.Connection) -> dict:
    calls = _load_llm_calls(conn, [trace_id])
    if not calls:
        raise HTTPException(404, f"trace {trace_id} not found")

    agent_ids = list(dict.fromkeys(call["agent_id"] or "unknown" for call in calls))
    events = [
        {
            "id": call["id"],
            "sequence": index + 1,
            "event_type": "llm_call",
            "phase_trace_id": trace_id,
            "agent_id": call["agent_id"] or "unknown",
            "parent_agent_id": "",
            "status": call["status"],
            "name": call["model"],
            "payload": {
                "llm_call_id": call["id"],
                "input_tokens": call["input_tokens"],
                "output_tokens": call["output_tokens"],
                "cost_usd": call["cost_usd"],
                "latency_ms": call["latency_ms"],
            },
            "created_at": call["created_at"],
        }
        for index, call in enumerate(calls)
    ]
    return {
        "trace_id": trace_id,
        "requested_trace_id": trace_id,
        "scope": "legacy_phase",
        "session_id": calls[0]["session_id"],
        "user_input": None,
        "events": events,
        "agents": [
            {
                "agent_id": agent_id,
                "phase_trace_ids": [trace_id],
                "call_count": sum(1 for call in calls if (call["agent_id"] or "unknown") == agent_id),
                "timeline": [
                    event for event in events if event["agent_id"] == agent_id
                ],
            }
            for agent_id in agent_ids
        ],
        "errors": [event for event in events if event["status"] == "error"],
        "evidence": {"retrievals": [], "citations": []},
        "trust": {
            "status": "partial",
            "score": 20,
            "ledger": {"valid": False, "event_count": 0, "head_hash": "", "issues": ["legacy_trace"]},
            "missing_required_events": [
                "trace_start",
                "input_received",
                "context_assembled",
                "agent_start",
                "agent_end",
                "verdict",
                "trace_end",
            ],
            "structural_issues": ["legacy_trace"],
            "open_tool_calls": [],
            "error_count": sum(1 for call in calls if call["status"] == "error"),
            "warning_count": 0,
            "retrieved_note_count": 0,
            "verified_citation_count": 0,
            "citation_coverage": None,
            "claim": "legacy LLM-call record; full-chain integrity unavailable",
        },
        "summary": {
            "total_tokens": sum(call["input_tokens"] + call["output_tokens"] for call in calls),
            "total_cost_usd": round(sum(call["cost_usd"] for call in calls), 6),
            "total_latency_ms": sum(call["latency_ms"] for call in calls),
            # Legacy records only contain completed LLM calls, so cumulative
            # model latency is the most honest available duration estimate.
            "wall_clock_ms": sum(call["latency_ms"] for call in calls),
            "call_count": len(calls),
            "tool_count": 0,
            "retrieval_count": 0,
            "handoff_count": 0,
            "agent_count": len(agent_ids),
            "verdict": "legacy",
            "status": "error" if any(call["status"] == "error" for call in calls) else "partial",
            "started_at": calls[0]["created_at"],
            "ended_at": calls[-1]["created_at"],
        },
    }


@router.get("/traces/recent")
def list_traces(limit: int = 50, conn: sqlite3.Connection = Depends(get_conn)):
    limit = max(1, min(limit, 100))
    roots = conn.execute(
        """
        SELECT trace_id, session_id, MIN(created_at) AS started_at,
               MAX(created_at) AS ended_at, COUNT(*) AS event_count
        FROM trace_events
        GROUP BY trace_id, session_id
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    traces = []
    for root in roots:
        rows = _load_events(conn, root["trace_id"])
        decoded = [decode_event(row) for row in rows]
        trust = assess_trace(rows)
        phase_ids = list(dict.fromkeys(
            event["phase_trace_id"] for event in decoded if event["phase_trace_id"]
        ))
        calls = _load_llm_calls(conn, phase_ids)
        agents = list(dict.fromkeys(
            event["agent_id"]
            for event in decoded
            if event["agent_id"] and event["agent_id"] not in {"router", "user"}
        ))
        trace_end = next(
            (event for event in reversed(decoded) if event["event_type"] == "trace_end"),
            None,
        )
        input_event = next(
            (event for event in decoded if event["event_type"] == "input_received"),
            None,
        )
        traces.append({
            "trace_id": root["trace_id"],
            "session_id": root["session_id"],
            "agents": agents,
            "status": trust["status"],
            "trust_score": trust["score"],
            "event_count": root["event_count"],
            "call_count": len(calls),
            "tool_count": sum(1 for event in decoded if event["event_type"] == "tool_end"),
            "retrieval_count": sum(1 for event in decoded if event["event_type"] == "retrieval_completed"),
            "latency_ms": elapsed_ms(root["started_at"], root["ended_at"]),
            "model_latency_ms": sum(call["latency_ms"] for call in calls),
            "cost_usd": round(sum(call["cost_usd"] for call in calls), 6),
            "verdict": trace_end["name"] if trace_end else "incomplete",
            "started_at": root["started_at"],
            "ended_at": root["ended_at"],
            "legacy": False,
            "input_preview": (
                input_event["payload"].get("content_preview", "") if input_event else ""
            ),
        })

    remaining = limit - len(traces)
    if remaining > 0:
        known_phases = conn.execute(
            "SELECT DISTINCT phase_trace_id FROM trace_events WHERE phase_trace_id != ''"
        ).fetchall()
        excluded = {row["phase_trace_id"] for row in known_phases}
        legacy_rows = conn.execute(
            """
            SELECT trace_id, session_id, MIN(created_at) AS started_at,
                   MAX(created_at) AS ended_at, COUNT(*) AS call_count,
                   SUM(latency_ms) AS latency_ms, SUM(cost_usd) AS cost_usd
            FROM llm_calls
            WHERE trace_id != ''
            GROUP BY trace_id, session_id
            ORDER BY started_at DESC
            """
        ).fetchall()
        for row in legacy_rows:
            if row["trace_id"] in excluded:
                continue
            agents = conn.execute(
                "SELECT DISTINCT agent_id FROM llm_calls "
                "WHERE trace_id = ? AND agent_id != ''",
                (row["trace_id"],),
            ).fetchall()
            traces.append({
                "trace_id": row["trace_id"],
                "session_id": row["session_id"],
                "agents": [agent["agent_id"] for agent in agents],
                "status": "partial",
                "trust_score": 20,
                "event_count": 0,
                "call_count": row["call_count"],
                "tool_count": 0,
                "retrieval_count": 0,
                "latency_ms": row["latency_ms"] or 0,
                "cost_usd": round(row["cost_usd"] or 0, 6),
                "verdict": "legacy",
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "legacy": True,
                "input_preview": "",
            })
            if len(traces) >= limit:
                break

    traces.sort(key=lambda item: item["started_at"] or "", reverse=True)
    return {"traces": traces[:limit], "total": len(traces[:limit])}


@router.get("/traces/{requested_trace_id}")
def get_trace_detail(
    requested_trace_id: str,
    conn: sqlite3.Connection = Depends(get_conn),
):
    root_trace_id, requested_phase_id = _resolve_root_trace(conn, requested_trace_id)
    if not root_trace_id:
        return _legacy_trace_detail(requested_trace_id, conn)

    rows = _load_events(conn, root_trace_id)
    decoded_all = [decode_event(row) for row in rows]
    trust = assess_trace(rows)
    scoped_events = (
        [
            event
            for event in decoded_all
            if not event["phase_trace_id"] or event["phase_trace_id"] == requested_phase_id
        ]
        if requested_phase_id
        else decoded_all
    )

    phase_ids = (
        [requested_phase_id]
        if requested_phase_id
        else list(dict.fromkeys(
            event["phase_trace_id"] for event in decoded_all if event["phase_trace_id"]
        ))
    )
    calls = _load_llm_calls(conn, phase_ids)
    agent_ids = list(dict.fromkeys(
        event["agent_id"]
        for event in scoped_events
        if event["agent_id"] and event["agent_id"] not in {"router", "user"}
    ))

    input_event = next(
        (event for event in decoded_all if event["event_type"] == "input_received"),
        None,
    )
    trace_end = next(
        (event for event in reversed(decoded_all) if event["event_type"] == "trace_end"),
        None,
    )
    retrievals = [
        event for event in scoped_events if event["event_type"] == "retrieval_completed"
    ]
    citations = []
    for event in scoped_events:
        if event["event_type"] != "citation_verified":
            continue
        citations.append({
            "note_id": event["payload"].get("note_id", event["name"]),
            "agent_id": event["agent_id"],
            "verification": event["payload"].get("method", "exact_note_id"),
            "sequence": event["sequence"],
        })

    return {
        "trace_id": root_trace_id,
        "requested_trace_id": requested_trace_id,
        "scope": "phase" if requested_phase_id else "root",
        "session_id": rows[0]["session_id"] if rows else "",
        "user_input": (
            {
                "content": input_event["payload"].get("content_preview", ""),
                "sha256": input_event["payload"].get("content_sha256", ""),
                "truncated": input_event["payload"].get("truncated", False),
                "created_at": input_event["created_at"],
            }
            if input_event
            else None
        ),
        "events": scoped_events,
        "agents": [
            {
                "agent_id": agent_id,
                "phase_trace_ids": list(dict.fromkeys(
                    event["phase_trace_id"]
                    for event in scoped_events
                    if event["agent_id"] == agent_id and event["phase_trace_id"]
                )),
                "call_count": sum(1 for call in calls if (call["agent_id"] or "unknown") == agent_id),
                "timeline": [
                    event for event in scoped_events if event["agent_id"] == agent_id
                ],
            }
            for agent_id in agent_ids
        ],
        "errors": [
            event
            for event in scoped_events
            if event["event_type"] == "error" or event["status"] == "error"
        ],
        "evidence": {
            "retrievals": retrievals,
            "citations": citations,
        },
        "trust": trust,
        "summary": {
            "total_tokens": sum(call["input_tokens"] + call["output_tokens"] for call in calls),
            "total_cost_usd": round(sum(call["cost_usd"] for call in calls), 6),
            "total_latency_ms": sum(call["latency_ms"] for call in calls),
            "wall_clock_ms": elapsed_ms(rows[0]["created_at"], rows[-1]["created_at"]),
            "call_count": len(calls),
            "tool_count": sum(1 for event in scoped_events if event["event_type"] == "tool_end"),
            "retrieval_count": len(retrievals),
            "handoff_count": sum(1 for event in scoped_events if event["event_type"] == "handoff"),
            "agent_count": len(agent_ids),
            "verdict": trace_end["name"] if trace_end else "incomplete",
            "status": trace_end["status"] if trace_end else "incomplete",
            "started_at": rows[0]["created_at"],
            "ended_at": rows[-1]["created_at"],
        },
    }
