"""
WorklistRegistry — A2A 任务持久化层。

对应 Clowder 的 WorklistRegistry.ts。
当 Agent A handoff 到 Agent B 时，先将任务写入 SQLite worklist 表，
Agent B 执行完成后标记 done。进程崩了重启后，pending/running 项可恢复。

安全：单个 Agent 崩溃不丢整个 session 的任务链。
"""

import json
import sqlite3
import uuid
from typing import Optional


# ── Write operations ──────────────────────────────────────

def save_handoff(
    conn: sqlite3.Connection,
    session_id: str,
    agent_id: str,
    depth: int,
    user_input: str,
    agent_a_output: str,
    mention_content: str,
    tool_events: list[dict],
    agent_a_id: str = "",
    proposal_id: str = "",
) -> str:
    """Persist one authorized handoff with an idempotent execution record."""
    idempotency_key = ""
    if proposal_id:
        from src.agent.governance import ensure_execution

        _, idempotency_key, execution_status = ensure_execution(
            conn,
            proposal_id=proposal_id,
            action_type="handoff",
            actor_id="orchestrator",
            request_payload={
                "session_id": session_id,
                "source_agent_id": agent_a_id,
                "target_agent_id": agent_id,
                "depth": depth,
                "objective": mention_content,
            },
        )
        existing = conn.execute(
            "SELECT id FROM worklist WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        if existing:
            return existing["id"]
        if execution_status == "succeeded":
            existing = conn.execute(
                "SELECT id FROM worklist WHERE proposal_id=? ORDER BY created_at LIMIT 1",
                (proposal_id,),
            ).fetchone()
            return existing["id"] if existing else ""

    wid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO worklist
           (id, session_id, agent_id, depth, status,
            user_input, agent_a_output, mention_content, tool_events_json,
            agent_a_id, proposal_id, idempotency_key)
           VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)""",
        (
            wid, session_id, agent_id, depth,
            user_input, agent_a_output, mention_content,
            json.dumps(tool_events, ensure_ascii=False),
            agent_a_id,
            proposal_id,
            idempotency_key,
        ),
    )
    conn.commit()
    return wid


def mark_running(conn: sqlite3.Connection, wid: str) -> None:
    conn.execute(
        "UPDATE worklist SET status='running', updated_at=datetime('now','localtime') WHERE id=?",
        (wid,),
    )
    conn.commit()
    _sync_execution(conn, wid, "running")


def mark_done(conn: sqlite3.Connection, wid: str) -> None:
    conn.execute(
        "UPDATE worklist SET status='done', updated_at=datetime('now','localtime') WHERE id=?",
        (wid,),
    )
    conn.commit()
    _sync_execution(conn, wid, "succeeded", result={"work_id": wid})
    conn.execute(
        """UPDATE handoff_proposals SET status='executed',
           updated_at=datetime('now','localtime')
           WHERE id=(SELECT proposal_id FROM worklist WHERE id=?) AND id != ''""",
        (wid,),
    )
    conn.commit()


def mark_failed(conn: sqlite3.Connection, wid: str, error_msg: str = "") -> None:
    conn.execute(
        "UPDATE worklist SET status='failed', error_msg=?, updated_at=datetime('now','localtime') WHERE id=?",
        (error_msg, wid),
    )
    conn.commit()
    _sync_execution(conn, wid, "failed", error_msg=error_msg)


def _sync_execution(
    conn: sqlite3.Connection,
    wid: str,
    status: str,
    *,
    result: dict | None = None,
    error_msg: str = "",
) -> None:
    row = conn.execute(
        "SELECT idempotency_key FROM worklist WHERE id=?",
        (wid,),
    ).fetchone()
    if not row or not row["idempotency_key"]:
        return
    from src.agent.governance import mark_execution

    mark_execution(
        conn,
        row["idempotency_key"],
        status,
        result=result,
        error_msg=error_msg,
    )


# ── Read operations ───────────────────────────────────────

def get_pending(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """获取 session 下所有未完成的 handoff（pending + running），按创建时间正序。"""
    rows = conn.execute(
        """SELECT * FROM worklist
           WHERE session_id=? AND status IN ('pending','running')
           ORDER BY created_at ASC""",
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_by_id(conn: sqlite3.Connection, wid: str) -> Optional[dict]:
    row = conn.execute("SELECT * FROM worklist WHERE id=?", (wid,)).fetchone()
    return dict(row) if row else None


# ── Cleanup ───────────────────────────────────────────────

def cleanup_session(conn: sqlite3.Connection, session_id: str) -> int:
    """清理已完成/失败的 worklist 项，返回删除数。"""
    cur = conn.execute(
        "DELETE FROM worklist WHERE session_id=? AND status IN ('done','failed')",
        (session_id,),
    )
    conn.commit()
    return cur.rowcount
