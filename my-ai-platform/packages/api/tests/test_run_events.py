import sqlite3
import unittest

from src.agent.run_events import (
    append_run_event,
    create_run,
    list_run_events,
    verify_run_event_chain,
)
from src.db.schema import init_db


class RunEventStoreTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.run_id = create_run(
            self.conn,
            session_id="session-runtime",
            prompt_version="v4",
        )

    def tearDown(self):
        self.conn.close()

    def test_events_are_strictly_ordered_and_resumable(self):
        append_run_event(
            self.conn,
            run_id=self.run_id,
            event_type="run.started",
            data={"status": "running"},
        )
        append_run_event(
            self.conn,
            run_id=self.run_id,
            event_type="agent.started",
            branch_id="root",
            agent_id="knowledge",
        )

        events = list_run_events(self.conn, self.run_id)
        self.assertEqual([event["sequence"] for event in events], [1, 2])
        self.assertEqual(
            [event["sequence"] for event in list_run_events(
                self.conn, self.run_id, after_sequence=1
            )],
            [2],
        )
        self.assertTrue(verify_run_event_chain(self.conn, self.run_id))

    def test_hash_chain_detects_payload_tampering(self):
        append_run_event(
            self.conn,
            run_id=self.run_id,
            event_type="run.started",
            data={"status": "running"},
        )
        self.conn.execute(
            "UPDATE run_events SET payload_json='{}' WHERE run_id=?",
            (self.run_id,),
        )
        self.conn.commit()
        self.assertFalse(verify_run_event_chain(self.conn, self.run_id))


if __name__ == "__main__":
    unittest.main()
