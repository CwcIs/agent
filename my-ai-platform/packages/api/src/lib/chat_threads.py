"""Read models for isolated chat workspaces."""

import sqlite3


def list_threads(conn: sqlite3.Connection, limit: int = 30) -> dict:
    safe_limit = max(1, min(limit, 100))
    rows = conn.execute(
        """
        SELECT
            messages.session_id AS session_id,
            COUNT(*) AS message_count,
            MAX(messages.created_at) AS updated_at,
            COALESCE(NULLIF(thread.title, ''), (
                SELECT content
                FROM messages first_message
                WHERE first_message.session_id = messages.session_id
                  AND first_message.role = 'user'
                ORDER BY first_message.created_at ASC
                LIMIT 1
            ), 'Untitled thought') AS title,
            (
                SELECT content
                FROM messages last_message
                WHERE last_message.session_id = messages.session_id
                  AND last_message.role IN ('user', 'assistant')
                ORDER BY last_message.created_at DESC
                LIMIT 1
            ) AS preview,
            GROUP_CONCAT(DISTINCT agent_id) AS agent_ids,
            COALESCE(thread.pinned, 0) AS pinned
        FROM messages
        LEFT JOIN chat_threads thread ON thread.session_id = messages.session_id
        WHERE COALESCE(thread.archived, 0) = 0
        GROUP BY messages.session_id
        ORDER BY pinned DESC, updated_at DESC
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
                "pinned": bool(row["pinned"]),
                "agent_ids": [
                    value
                    for value in (row["agent_ids"] or "").split(",")
                    if value and value not in {"user", "tool"}
                ],
            }
            for row in rows
        ]
    }


def update_thread(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    title: str | None = None,
    pinned: bool | None = None,
    archived: bool | None = None,
) -> dict:
    exists = conn.execute(
        "SELECT 1 FROM messages WHERE session_id = ? LIMIT 1",
        (session_id,),
    ).fetchone()
    if not exists:
        raise LookupError("thread not found")

    conn.execute(
        "INSERT INTO chat_threads (session_id) VALUES (?) "
        "ON CONFLICT(session_id) DO NOTHING",
        (session_id,),
    )
    updates: list[str] = []
    values: list[object] = []
    if title is not None:
        updates.append("title = ?")
        values.append(title.strip()[:80])
    if pinned is not None:
        updates.append("pinned = ?")
        values.append(int(pinned))
    if archived is not None:
        updates.append("archived = ?")
        values.append(int(archived))
    if updates:
        updates.append("updated_at = datetime('now','localtime')")
        values.append(session_id)
        conn.execute(
            f"UPDATE chat_threads SET {', '.join(updates)} WHERE session_id = ?",
            values,
        )
    conn.commit()
    row = conn.execute(
        "SELECT session_id, title, pinned, archived, updated_at "
        "FROM chat_threads WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return {
        "session_id": row["session_id"],
        "title": row["title"],
        "pinned": bool(row["pinned"]),
        "archived": bool(row["archived"]),
        "updated_at": row["updated_at"],
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
