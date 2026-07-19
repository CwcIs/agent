"""Shared trace instrumentation for serial and parallel Agent execution."""

import json
import sqlite3

from src.lib.trace import content_fingerprint, record_trace_event


def record_tool_trace(
    conn: sqlite3.Connection | None,
    *,
    root_trace_id: str,
    phase_trace_id: str,
    session_id: str,
    agent_id: str,
    event: dict,
) -> None:
    status = "ok"
    if event.get("type") == "tool_end":
        try:
            parsed = json.loads(event.get("result", "") or "{}")
            if isinstance(parsed, dict) and (
                parsed.get("status") == "error" or parsed.get("error")
            ):
                status = "error"
        except (TypeError, json.JSONDecodeError):
            pass

    record_trace_event(
        conn,
        event["type"],
        trace_id=root_trace_id,
        phase_trace_id=phase_trace_id,
        session_id=session_id,
        agent_id=agent_id,
        status=status,
        name=event.get("name", "unknown"),
        payload={
            "tool_call_id": event.get("tool_call_id", ""),
            "input": event.get("input", {}),
            "result": event.get("result", "") if event["type"] == "tool_end" else "",
        },
    )


def _retrieved_note_ids(
    conn: sqlite3.Connection | None,
    root_trace_id: str,
) -> list[str]:
    if conn is None or not root_trace_id:
        return []

    note_ids: list[str] = []
    rows = conn.execute(
        "SELECT payload_json FROM trace_events "
        "WHERE trace_id = ? AND event_type = 'retrieval_completed'",
        (root_trace_id,),
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
            note_ids.extend(
                item.get("note_id", "")
                for item in payload.get("selected", [])
                if isinstance(item, dict)
            )
        except (TypeError, json.JSONDecodeError):
            pass
    return list(dict.fromkeys(note_id for note_id in note_ids if note_id))


def record_agent_output_trace(
    conn: sqlite3.Connection | None,
    *,
    root_trace_id: str,
    phase_trace_id: str,
    session_id: str,
    agent_id: str,
    full_text: str,
    tool_call_count: int = 0,
    depth: int | None = None,
    mode: str = "serial",
    parent_agent_id: str = "",
) -> tuple[list[str], list[str]]:
    retrieved_note_ids = _retrieved_note_ids(conn, root_trace_id)
    cited_note_ids = [
        note_id for note_id in retrieved_note_ids if note_id in full_text
    ]

    if conn is not None and cited_note_ids:
        from src.lib.ranker import record_event

        for note_id in cited_note_ids:
            record_event(conn, note_id, "cited", source="search")
            record_trace_event(
                conn,
                "citation_verified",
                trace_id=root_trace_id,
                phase_trace_id=phase_trace_id,
                session_id=session_id,
                agent_id=agent_id,
                name=note_id,
                payload={"note_id": note_id, "method": "exact_note_id"},
            )

    payload = {
        "mode": mode,
        "output_chars": len(full_text),
        "output_sha256": content_fingerprint(full_text),
        "tool_call_count": tool_call_count,
        "retrieved_note_ids": retrieved_note_ids,
        "explicitly_cited_note_ids": cited_note_ids,
        "citation_verification": (
            "exact_note_id" if cited_note_ids else "not_verified"
        ),
    }
    if depth is not None:
        payload["depth"] = depth

    record_trace_event(
        conn,
        "agent_end",
        trace_id=root_trace_id,
        phase_trace_id=phase_trace_id,
        session_id=session_id,
        agent_id=agent_id,
        parent_agent_id=parent_agent_id,
        payload=payload,
    )
    return retrieved_note_ids, cited_note_ids

