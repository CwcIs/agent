"""Durable, hash-linked event ledger for router runs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _event_hash(previous_hash: str, envelope: dict[str, Any]) -> str:
    content = f"{previous_hash}:{_json(envelope)}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def create_run(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    prompt_version: str,
    run_id: str | None = None,
) -> str:
    persisted_run_id = run_id or str(uuid.uuid4())
    conn.execute(
        """INSERT INTO agent_runs
           (id, session_id, status, current_node, prompt_version, started_at)
           VALUES (?, ?, 'created', 'accept_input', ?, ?)""",
        (
            persisted_run_id,
            session_id,
            prompt_version,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return persisted_run_id


def append_run_event(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    event_type: str,
    data: dict[str, Any] | None = None,
    branch_id: str = "",
    node_name: str = "",
    agent_id: str = "",
) -> dict[str, Any]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        last = conn.execute(
            """SELECT sequence, event_hash FROM run_events
               WHERE run_id=? ORDER BY sequence DESC LIMIT 1""",
            (run_id,),
        ).fetchone()
        sequence = int(last["sequence"]) + 1 if last else 1
        previous_hash = str(last["event_hash"]) if last else ""
        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        envelope = {
            "event_id": event_id,
            "run_id": run_id,
            "branch_id": branch_id,
            "sequence": sequence,
            "type": event_type,
            "timestamp": timestamp,
            "node_name": node_name,
            "agent_id": agent_id,
            "data": data or {},
        }
        event_hash = _event_hash(previous_hash, envelope)
        conn.execute(
            """INSERT INTO run_events
               (id, run_id, branch_id, sequence, event_type, node_name, agent_id,
                payload_json, previous_hash, event_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                run_id,
                branch_id,
                sequence,
                event_type,
                node_name,
                agent_id,
                _json(data or {}),
                previous_hash,
                event_hash,
                timestamp,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return envelope


def list_run_events(
    conn: sqlite3.Connection, run_id: str, *, after_sequence: int = 0
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT id, run_id, branch_id, sequence, event_type, node_name,
                  agent_id, payload_json, created_at
           FROM run_events
           WHERE run_id=? AND sequence>?
           ORDER BY sequence""",
        (run_id, max(0, after_sequence)),
    ).fetchall()
    return [
        {
            "event_id": row["id"],
            "run_id": row["run_id"],
            "branch_id": row["branch_id"],
            "sequence": row["sequence"],
            "type": row["event_type"],
            "timestamp": row["created_at"],
            "node_name": row["node_name"],
            "agent_id": row["agent_id"],
            "data": json.loads(row["payload_json"]),
        }
        for row in rows
    ]


def verify_run_event_chain(conn: sqlite3.Connection, run_id: str) -> bool:
    rows = conn.execute(
        """SELECT id, run_id, branch_id, sequence, event_type, node_name,
                  agent_id, payload_json, previous_hash, event_hash, created_at
           FROM run_events WHERE run_id=? ORDER BY sequence""",
        (run_id,),
    ).fetchall()
    previous_hash = ""
    for expected_sequence, row in enumerate(rows, start=1):
        envelope = {
            "event_id": row["id"],
            "run_id": row["run_id"],
            "branch_id": row["branch_id"],
            "sequence": row["sequence"],
            "type": row["event_type"],
            "timestamp": row["created_at"],
            "node_name": row["node_name"],
            "agent_id": row["agent_id"],
            "data": json.loads(row["payload_json"]),
        }
        if row["sequence"] != expected_sequence or row["previous_hash"] != previous_hash:
            return False
        if row["event_hash"] != _event_hash(previous_hash, envelope):
            return False
        previous_hash = row["event_hash"]
    return True
