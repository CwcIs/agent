import json
import sqlite3
import unittest

from src.lib.trace import (
    assess_trace,
    canonical_payload,
    record_trace_event,
    set_trace_context,
    verify_trace_chain,
)


TRACE_SCHEMA = """
CREATE TABLE trace_events (
    id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    phase_trace_id TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    agent_id TEXT NOT NULL DEFAULT '',
    parent_agent_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ok',
    name TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    prev_hash TEXT NOT NULL DEFAULT '',
    event_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trace_id, sequence)
);
"""


class TraceLedgerTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(TRACE_SCHEMA)
        set_trace_context("root-1", "phase-1", "session-1", "knowledge")

    def tearDown(self):
        self.conn.close()

    def rows(self):
        return self.conn.execute(
            "SELECT * FROM trace_events ORDER BY sequence"
        ).fetchall()

    def record_complete_trace(self):
        events = [
            ("trace_start", "router"),
            ("input_received", "user"),
            ("context_assembled", "knowledge"),
            ("agent_start", "knowledge"),
            ("verdict", "knowledge"),
            ("agent_end", "knowledge"),
            ("trace_end", "router"),
        ]
        for event_type, agent_id in events:
            record_trace_event(
                self.conn,
                event_type,
                agent_id=agent_id,
                payload={"event": event_type},
            )

    def test_complete_ledger_is_verified(self):
        self.record_complete_trace()

        verification = verify_trace_chain(self.rows())
        assessment = assess_trace(self.rows())

        self.assertTrue(verification["valid"])
        self.assertEqual(assessment["status"], "verified")
        self.assertEqual(assessment["score"], 100)
        self.assertEqual(assessment["missing_required_events"], [])

    def test_payload_tampering_is_detected(self):
        self.record_complete_trace()
        self.conn.execute(
            "UPDATE trace_events SET payload_json = ? WHERE sequence = 3",
            (json.dumps({"event": "tampered"}),),
        )
        self.conn.commit()

        verification = verify_trace_chain(self.rows())

        self.assertFalse(verification["valid"])
        self.assertTrue(
            any(issue.startswith("event_hash_mismatch:3") for issue in verification["issues"])
        )
        self.assertEqual(assess_trace(self.rows())["status"], "compromised")

    def test_unclosed_tool_call_marks_trace_partial(self):
        self.record_complete_trace()
        record_trace_event(
            self.conn,
            "tool_start",
            name="search_notes",
            payload={"tool_call_id": "tool-1"},
        )

        assessment = assess_trace(self.rows())

        self.assertEqual(assessment["status"], "partial")
        self.assertEqual(assessment["open_tool_calls"][0]["tool_call_id"], "tool-1")

    def test_sensitive_payload_fields_are_redacted(self):
        payload = json.loads(
            canonical_payload({
                "authorization": "Bearer secret",
                "api_key": "secret-key",
                "message": "request failed with Bearer abc.def.ghi",
                "input_tokens": 42,
            })
        )

        self.assertEqual(payload["authorization"], "[REDACTED]")
        self.assertEqual(payload["api_key"], "[REDACTED]")
        self.assertEqual(payload["message"], "request failed with [REDACTED]")
        self.assertEqual(payload["input_tokens"], 42)

    def test_retrieval_and_exact_citation_are_linked(self):
        for event_type, agent_id in [
            ("trace_start", "router"),
            ("input_received", "user"),
            ("context_assembled", "knowledge"),
            ("agent_start", "knowledge"),
        ]:
            record_trace_event(self.conn, event_type, agent_id=agent_id)
        record_trace_event(
            self.conn,
            "retrieval_completed",
            payload={"selected": [{"note_id": "note-1"}]},
        )
        record_trace_event(
            self.conn,
            "citation_verified",
            name="note-1",
            payload={"note_id": "note-1", "method": "exact_note_id"},
        )
        for event_type, agent_id in [
            ("verdict", "knowledge"),
            ("agent_end", "knowledge"),
            ("trace_end", "router"),
        ]:
            record_trace_event(self.conn, event_type, agent_id=agent_id)

        assessment = assess_trace(self.rows())

        self.assertEqual(assessment["retrieved_note_count"], 1)
        self.assertEqual(assessment["verified_citation_count"], 1)
        self.assertEqual(assessment["citation_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
