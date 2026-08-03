import sqlite3
import unittest

from src.lib.chat_threads import get_history, list_threads, update_thread


def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE chat_threads (
            session_id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            pinned INTEGER NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return conn


class ChatThreadRoutesTest(unittest.TestCase):
    def setUp(self):
        self.conn = make_conn()
        self.conn.executemany(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("1", "older", "knowledge", "user", "First workspace question", "2026-07-26 10:00:00"),
                ("2", "older", "knowledge", "assistant", "First answer", "2026-07-26 10:01:00"),
                ("3", "newer", "knowledge", "user", "Review this assumption", "2026-07-27 11:00:00"),
                ("4", "newer", "review", "assistant", "The assumption is weak", "2026-07-27 11:01:00"),
            ],
        )

    def tearDown(self):
        self.conn.close()

    def test_threads_are_recent_first_and_derive_title_from_first_user_message(self):
        result = list_threads(self.conn, limit=30)

        self.assertEqual(["newer", "older"], [item["session_id"] for item in result["threads"]])
        self.assertEqual("Review this assumption", result["threads"][0]["title"])
        self.assertEqual(2, result["threads"][0]["message_count"])
        self.assertEqual({"knowledge", "review"}, set(result["threads"][0]["agent_ids"]))

    def test_history_is_isolated_by_session(self):
        result = get_history(self.conn, session_id="newer")

        self.assertEqual("newer", result["session_id"])
        self.assertEqual(["Review this assumption", "The assumption is weak"], [
            message["content"] for message in result["messages"]
        ])
        self.assertNotIn("First answer", [message["content"] for message in result["messages"]])

    def test_thread_metadata_controls_title_order_and_archiving(self):
        update_thread(self.conn, "older", title="Pinned research", pinned=True)
        result = list_threads(self.conn)
        self.assertEqual("older", result["threads"][0]["session_id"])
        self.assertEqual("Pinned research", result["threads"][0]["title"])
        self.assertTrue(result["threads"][0]["pinned"])

        update_thread(self.conn, "older", archived=True)
        result = list_threads(self.conn)
        self.assertEqual(["newer"], [item["session_id"] for item in result["threads"]])


if __name__ == "__main__":
    unittest.main()
