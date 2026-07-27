"""Deterministic policy gates for Agent handoffs and side-effect execution."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any

POLICY_VERSION = "gate-v2.1"

DECISION_ALLOW = "allow"
DECISION_ASK_USER = "ask_user"
DECISION_DEGRADE = "degrade"
DECISION_DENY = "deny"

_SENSITIVE_RE = re.compile(
    r"(?i)(password|passwd|api[_ -]?key|access[_ -]?token|secret|"
    r"身份证|银行卡|密码|密钥|私密|机密)"
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PolicyDecision:
    proposal_id: str
    outcome: str
    effective_risk: str
    reason: str
    policy_version: str = POLICY_VERSION

    @property
    def allowed(self) -> bool:
        return self.outcome == DECISION_ALLOW


def create_handoff_proposal(
    conn: sqlite3.Connection,
    *,
    trace_id: str,
    phase_trace_id: str,
    session_id: str,
    source_agent_id: str,
    target_agent_id: str,
    objective: str,
    depth: int,
    input_refs: list[str] | None = None,
    trigger_type: str = "explicit",
) -> dict[str, Any]:
    """Persist an Agent request as data. Creating it never schedules execution."""
    proposal_id = str(uuid.uuid4())
    requested_capabilities = ["knowledge.read"]
    data_sensitivity = "sensitive" if _SENSITIVE_RE.search(objective) else "normal"
    persisted_objective = (
        "[REDACTED:SENSITIVE_HANDOFF_OBJECTIVE]"
        if data_sensitivity == "sensitive"
        else objective
    )
    payload = {
        "source_agent_id": source_agent_id,
        "target_agent_id": target_agent_id,
        "objective": objective,
        "data_sensitivity": data_sensitivity,
        "depth": depth,
        "input_refs": input_refs or [],
        "requested_capabilities": requested_capabilities,
        "trigger_type": trigger_type,
    }
    proposal_hash = _fingerprint(payload)
    conn.execute(
        """INSERT INTO handoff_proposals
           (id, trace_id, phase_trace_id, session_id, source_agent_id,
            target_agent_id, objective, input_refs_json,
            requested_capabilities_json, trigger_type, data_sensitivity,
            depth, proposal_hash, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed')""",
        (
            proposal_id,
            trace_id,
            phase_trace_id,
            session_id,
            source_agent_id,
            target_agent_id,
            persisted_objective,
            _canonical_json(input_refs or []),
            _canonical_json(requested_capabilities),
            trigger_type,
            data_sensitivity,
            depth,
            proposal_hash,
        ),
    )
    conn.commit()
    return {"id": proposal_id, "proposal_hash": proposal_hash, **payload}


def evaluate_handoff_proposal(
    conn: sqlite3.Connection,
    proposal: dict[str, Any],
    *,
    valid_agent_ids: list[str],
    max_depth: int,
) -> PolicyDecision:
    """Apply the G2 policy gate without relying on model judgment."""
    target = str(proposal["target_agent_id"])
    source = str(proposal["source_agent_id"])
    objective = str(proposal.get("objective", ""))
    depth = int(proposal.get("depth", 0))
    trigger_type = str(proposal.get("trigger_type", "explicit"))

    if trigger_type == "shadow":
        outcome, risk, reason = (
            DECISION_DEGRADE,
            "R1",
            "shadow_mention_requires_explicit_handoff",
        )
    elif target not in set(valid_agent_ids):
        outcome, risk, reason = DECISION_DENY, "R3", "target_agent_not_registered"
    elif target == source:
        outcome, risk, reason = DECISION_DENY, "R2", "self_handoff_not_allowed"
    elif depth + 1 >= max_depth:
        outcome, risk, reason = DECISION_DENY, "R2", "handoff_depth_limit"
    elif proposal.get("data_sensitivity") == "sensitive":
        outcome, risk, reason = (
            DECISION_ASK_USER,
            "R3",
            "sensitive_data_requires_explicit_approval",
        )
    else:
        outcome, risk, reason = DECISION_ALLOW, "R1", "internal_read_only_handoff"

    dimensions = {
        "action": "internal_handoff",
        "data_sensitivity": proposal.get("data_sensitivity", "normal"),
        "target_domain": "registered_agent",
        "permission_scope": "knowledge.read",
        "blast_radius": "current_session",
        "cost": "bounded",
        "trigger_type": trigger_type,
    }
    decision_id = str(uuid.uuid4())
    decision = PolicyDecision(
        proposal_id=str(proposal["id"]),
        outcome=outcome,
        effective_risk=risk,
        reason=reason,
    )
    conn.execute(
        """INSERT INTO policy_decisions
           (id, proposal_id, policy_version, outcome, effective_risk,
            reason, dimensions_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            decision_id,
            decision.proposal_id,
            decision.policy_version,
            decision.outcome,
            decision.effective_risk,
            decision.reason,
            _canonical_json(dimensions),
        ),
    )
    conn.execute(
        """UPDATE handoff_proposals
           SET status=?, policy_version=?, decision_reason=?,
               updated_at=datetime('now','localtime')
           WHERE id=?""",
        (
            decision.outcome,
            decision.policy_version,
            decision.reason,
            decision.proposal_id,
        ),
    )
    conn.commit()
    return decision


def ensure_execution(
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    action_type: str,
    actor_id: str,
    request_payload: dict[str, Any],
) -> tuple[str, str, str]:
    """Create one execution ledger row per proposal and return its current state."""
    idempotency_key = f"{action_type}:{proposal_id}"
    existing = conn.execute(
        "SELECT id, status FROM execution_ledger WHERE idempotency_key=?",
        (idempotency_key,),
    ).fetchone()
    if existing:
        return existing["id"], idempotency_key, existing["status"]

    execution_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO execution_ledger
           (id, proposal_id, idempotency_key, action_type, actor_id,
            request_hash, request_json, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (
            execution_id,
            proposal_id,
            idempotency_key,
            action_type,
            actor_id,
            _fingerprint(request_payload),
            _canonical_json(request_payload),
        ),
    )
    conn.commit()
    return execution_id, idempotency_key, "pending"


def mark_execution(
    conn: sqlite3.Connection,
    idempotency_key: str,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    error_msg: str = "",
) -> None:
    if not idempotency_key:
        return
    if status == "running":
        timing_sql = "started_at=COALESCE(started_at, datetime('now','localtime'))"
    elif status in {"succeeded", "failed", "compensated"}:
        timing_sql = "completed_at=datetime('now','localtime')"
    else:
        timing_sql = "updated_at=datetime('now','localtime')"
    conn.execute(
        f"""UPDATE execution_ledger
            SET status=?, result_json=?, error_msg=?, {timing_sql}
            WHERE idempotency_key=?""",
        (
            status,
            _canonical_json(result or {}),
            error_msg[:2000],
            idempotency_key,
        ),
    )
    conn.commit()
