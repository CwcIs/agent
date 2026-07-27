"""Read models for isolated chat workspaces."""

import sqlite3


def list_threads(conn: sqlite3.Connection, limit: int = 30) -> dict:
    safe_limit = max(1, min(limit, 100))
    rows = conn.execute(
        """
        SELECT
            session_id,
            COUNT(*) AS message_count,
            MAX(created_at) AS updated_at,
            (
                SELECT content
                FROM messages first_message
                WHERE first_message.session_id = messages.session_id
                  AND first_message.role = 'user'
                ORDER BY first_message.created_at ASC
                LIMIT 1
            ) AS title,
            (
                SELECT content
                FROM messages last_message
                WHERE last_message.session_id = messages.session_id
                  AND last_message.role IN ('user', 'assistant')
                ORDER BY last_message.created_at DESC
                LIMIT 1
            ) AS preview,
            GROUP_CONCAT(DISTINCT agent_id) AS agent_ids
        FROM messages
        GROUP BY session_id
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (safe_limit,),
    ).fetchall()
    return {
        "threads": [
            {
                "session_id": row["session_id"],
                "title": (row["title"] or "Untitled thought").strip()[:80],
                "preview": (row["preview"] or "").strip()[:140],
                "message_count": row["message_count"],
                "updated_at": row["updated_at"],
                "agent_ids": [
                    value
                    for value in (row["agent_ids"] or "").split(",")
                    if value and value not in {"user", "tool"}
                ],
            }
            for row in rows
        ]
    }


def get_history(conn: sqlite3.Connection, session_id: str) -> dict:
    rows = conn.execute(
        """
        SELECT id, role, agent_id, content, created_at
        FROM messages
        WHERE session_id = ? AND role IN ('user', 'assistant')
        ORDER BY created_at ASC, id ASC
        LIMIT 300
        """,
        (session_id,),
    ).fetchall()
    return {
        "session_id": session_id,
        "messages": [
            {
                "id": row["id"],
                "role": row["role"],
                "agent_id": row["agent_id"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            for row in rows
        ],
    }
