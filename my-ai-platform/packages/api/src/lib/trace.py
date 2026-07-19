"""Tamper-evident execution tracing for the complete Agent chain."""

import hashlib
import json
import logging
import re
import sqlite3
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_MAX_STRING = 2_000
_MAX_PAYLOAD = 12_000
_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "password",
    "secret",
    "access_token",
    "refresh_token",
    "cookie",
    "set-cookie",
}
_SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[a-z0-9._-]+"),
    re.compile(r"\bsk-[a-zA-Z0-9_-]{12,}\b"),
)


@dataclass(frozen=True)
class TraceContext:
    trace_id: str = ""
    phase_trace_id: str = ""
    session_id: str = ""
    agent_id: str = ""


_trace_context: ContextVar[TraceContext] = ContextVar(
    "trace_context",
    default=TraceContext(),
)


def set_trace_context(
    trace_id: str,
    phase_trace_id: str = "",
    session_id: str = "",
    agent_id: str = "",
) -> None:
    _trace_context.set(TraceContext(trace_id, phase_trace_id, session_id, agent_id))


def get_trace_context() -> TraceContext:
    return _trace_context.get()


def content_fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _sanitize(value: Any, key: str = "") -> Any:
    if key.lower() in _SENSITIVE_KEYS:
        return "[REDACTED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        redacted = value
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        if len(redacted) <= _MAX_STRING:
            return redacted
        return {
            "preview": redacted[:_MAX_STRING],
            "truncated": True,
            "char_count": len(redacted),
            "sha256": content_fingerprint(value),
        }
    if isinstance(value, dict):
        return {str(k): _sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value[:100]]
    return _sanitize(str(value), key)


def canonical_payload(payload: dict[str, Any] | None) -> str:
    sanitized = _sanitize(payload or {})
    encoded = json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded) <= _MAX_PAYLOAD:
        return encoded
    fallback = {
        "preview": encoded[:_MAX_PAYLOAD],
        "truncated": True,
        "char_count": len(encoded),
        "sha256": content_fingerprint(encoded),
    }
    return json.dumps(fallback, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _event_hash(
    prev_hash: str,
    trace_id: str,
    sequence: int,
    event_type: str,
    phase_trace_id: str,
    session_id: str,
    agent_id: str,
    parent_agent_id: str,
    status: str,
    name: str,
    payload_json: str,
) -> str:
    material = "|".join(
        [
            prev_hash,
            trace_id,
            str(sequence),
            event_type,
            phase_trace_id,
            session_id,
            agent_id,
            parent_agent_id,
            status,
            name,
            payload_json,
        ]
    )
    return content_fingerprint(material)


def record_trace_event(
    conn: sqlite3.Connection | None,
    event_type: str,
    *,
    trace_id: str = "",
    phase_trace_id: str = "",
    session_id: str = "",
    agent_id: str = "",
    parent_agent_id: str = "",
    status: str = "ok",
    name: str = "",
    payload: dict[str, Any] | None = None,
) -> str | None:
    """Append one event to the trace ledger without breaking the main workflow."""
    if conn is None:
        return None

    context = get_trace_context()
    root_id = trace_id or context.trace_id
    if not root_id:
        return None

    phase_id = phase_trace_id or context.phase_trace_id
    sid = session_id or context.session_id
    aid = agent_id or context.agent_id
    payload_json = canonical_payload(payload)

    try:
        previous = conn.execute(
            "SELECT sequence, event_hash FROM trace_events "
            "WHERE trace_id = ? ORDER BY sequence DESC LIMIT 1",
            (root_id,),
        ).fetchone()
        sequence = (previous["sequence"] if previous else 0) + 1
        prev_hash = previous["event_hash"] if previous else ""
        event_hash = _event_hash(
            prev_hash,
            root_id,
            sequence,
            event_type,
            phase_id,
            sid,
            aid,
            parent_agent_id,
            status,
            name,
            payload_json,
        )
        event_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO trace_events
               (id, trace_id, phase_trace_id, session_id, sequence, event_type,
                agent_id, parent_agent_id, status, name, payload_json,
                prev_hash, event_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                root_id,
                phase_id,
                sid,
                sequence,
                event_type,
                aid,
                parent_agent_id,
                status,
                name,
                payload_json,
                prev_hash,
                event_hash,
            ),
        )
        conn.commit()
        return event_id
    except Exception:
        logger.exception("trace event write failed trace=%s event=%s", root_id, event_type)
        return None


def decode_event(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    event = dict(row)
    try:
        event["payload"] = json.loads(event.pop("payload_json", "{}") or "{}")
    except (TypeError, json.JSONDecodeError):
        event["payload"] = {"decode_error": True}
    return event


def verify_trace_chain(rows: list[sqlite3.Row] | list[dict[str, Any]]) -> dict[str, Any]:
    """Verify sequence continuity and the complete event hash chain."""
    previous_hash = ""
    expected_sequence = 1
    issues: list[str] = []

    for raw in rows:
        row = dict(raw)
        sequence = int(row["sequence"])
        if sequence != expected_sequence:
            issues.append(f"sequence_gap:{expected_sequence}->{sequence}")
            expected_sequence = sequence

        if row.get("prev_hash", "") != previous_hash:
            issues.append(f"prev_hash_mismatch:{sequence}")

        expected_hash = _event_hash(
            previous_hash,
            row["trace_id"],
            sequence,
            row["event_type"],
            row.get("phase_trace_id", ""),
            row.get("session_id", ""),
            row.get("agent_id", ""),
            row.get("parent_agent_id", ""),
            row.get("status", ""),
            row.get("name", ""),
            row.get("payload_json", "{}"),
        )
        if row.get("event_hash") != expected_hash:
            issues.append(f"event_hash_mismatch:{sequence}")

        previous_hash = row.get("event_hash", "")
        expected_sequence += 1

    return {
        "valid": bool(rows) and not issues,
        "event_count": len(rows),
        "head_hash": previous_hash,
        "issues": issues,
    }


def assess_trace(rows: list[sqlite3.Row] | list[dict[str, Any]]) -> dict[str, Any]:
    """Build an honest trust assessment from ledger integrity and coverage."""
    ledger = verify_trace_chain(rows)
    decoded = [decode_event(row) for row in rows]
    event_types = {event["event_type"] for event in decoded}
    required = {
        "trace_start",
        "input_received",
        "context_assembled",
        "agent_start",
        "agent_end",
        "verdict",
        "trace_end",
    }
    missing = sorted(required - event_types)
    terminal_positions = [
        index for index, event in enumerate(decoded) if event["event_type"] == "trace_end"
    ]
    structural_issues: list[str] = []
    if len(terminal_positions) > 1:
        structural_issues.append("multiple_trace_end_events")
    if terminal_positions and terminal_positions[-1] != len(decoded) - 1:
        structural_issues.append("events_after_trace_end")

    open_tools: dict[str, dict[str, Any]] = {}
    for event in decoded:
        if event["event_type"] not in {"tool_start", "tool_end"}:
            continue
        payload = event.get("payload", {})
        call_id = payload.get("tool_call_id") or (
            f"{event.get('phase_trace_id', '')}:{event.get('name', '')}"
        )
        if event["event_type"] == "tool_start":
            open_tools[call_id] = event
        else:
            open_tools.pop(call_id, None)

    error_count = sum(
        1
        for event in decoded
        if event.get("status") == "error" or event["event_type"] == "error"
    )
    warning_count = sum(1 for event in decoded if event.get("status") == "warning")
    retrieved_ids: set[str] = set()
    cited_ids: set[str] = set()
    for event in decoded:
        payload = event.get("payload", {})
        if event["event_type"] == "retrieval_completed":
            retrieved_ids.update(
                item.get("note_id", "")
                for item in payload.get("selected", [])
                if isinstance(item, dict)
            )
        if event["event_type"] == "agent_end":
            cited_ids.update(payload.get("explicitly_cited_note_ids", []))
        if event["event_type"] == "citation_verified":
            cited_ids.add(payload.get("note_id", event.get("name", "")))
    retrieved_ids.discard("")
    cited_ids.discard("")

    if not ledger["valid"]:
        status = "compromised"
    elif missing or open_tools or structural_issues:
        status = "partial"
    elif error_count:
        status = "degraded"
    else:
        status = "verified"

    score = 100
    if not ledger["valid"]:
        score -= 60
    score -= min(30, len(missing) * 5)
    score -= min(20, len(structural_issues) * 10)
    score -= min(20, len(open_tools) * 10)
    score -= min(20, error_count * 5)
    score = max(0, score)

    return {
        "status": status,
        "score": score,
        "ledger": ledger,
        "missing_required_events": missing,
        "structural_issues": structural_issues,
        "open_tool_calls": [
            {
                "tool_call_id": key,
                "name": event.get("name", ""),
                "agent_id": event.get("agent_id", ""),
            }
            for key, event in open_tools.items()
        ],
        "error_count": error_count,
        "warning_count": warning_count,
        "retrieved_note_count": len(retrieved_ids),
        "verified_citation_count": len(cited_ids),
        "citation_coverage": (
            round(len(cited_ids) / len(retrieved_ids), 3) if retrieved_ids else None
        ),
        "claim": (
            "tamper-evident local ledger; not externally notarized"
            if ledger["valid"]
            else "ledger verification failed or unavailable"
        ),
    }
