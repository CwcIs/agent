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
) -> str:
    """持久化一个 pending A2A handoff，返回 worklist id。agent_a_id 记录触发方。"""
    wid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO worklist
           (id, session_id, agent_id, depth, status,
            user_input, agent_a_output, mention_content, tool_events_json, agent_a_id)
           VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)""",
        (
            wid, session_id, agent_id, depth,
            user_input, agent_a_output, mention_content,
            json.dumps(tool_events, ensure_ascii=False),
            agent_a_id,
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


def mark_done(conn: sqlite3.Connection, wid: str) -> None:
    conn.execute(
        "UPDATE worklist SET status='done', updated_at=datetime('now','localtime') WHERE id=?",
        (wid,),
    )
    conn.commit()


def mark_failed(conn: sqlite3.Connection, wid: str, error_msg: str = "") -> None:
    conn.execute(
        "UPDATE worklist SET status='failed', error_msg=?, updated_at=datetime('now','localtime') WHERE id=?",
        (error_msg, wid),
    )
    conn.commit()


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
