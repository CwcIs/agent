import sqlite3
import unittest
from unittest.mock import AsyncMock, patch

from src.agent.governance import (
    create_handoff_proposal,
    evaluate_handoff_proposal,
)
from src.agent.worklist import get_by_id, mark_done, mark_running, save_handoff
from src.context.assemble import _fetch_related_notes
from src.db.schema import init_db
from src.lib.knowledge_lifecycle import publish_candidate
from src.lib.trace import set_trace_context
from src.tools.notes import build_note_tools


class GovernanceGateTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def proposal(self, objective: str = "检查这个观点"):
        return create_handoff_proposal(
            self.conn,
            trace_id="trace-1",
            phase_trace_id="phase-1",
            session_id="session-1",
            source_agent_id="knowledge",
            target_agent_id="review",
            objective=objective,
            depth=0,
            input_refs=["trace:trace-1"],
        )

    def test_proposal_creation_does_not_schedule_work(self):
        proposal = self.proposal()
        count = self.conn.execute("SELECT COUNT(*) FROM worklist").fetchone()[0]
        self.assertEqual(count, 0)
        self.assertEqual(proposal["target_agent_id"], "review")

    def test_internal_read_only_handoff_is_allowed(self):
        proposal = self.proposal()
        decision = evaluate_handoff_proposal(
            self.conn,
            proposal,
            valid_agent_ids=["knowledge", "review", "brain"],
            max_depth=5,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.effective_risk, "R1")

    def test_sensitive_handoff_requires_explicit_approval(self):
        proposal = self.proposal("把我的 API key 和私密笔记交给 review")
        decision = evaluate_handoff_proposal(
            self.conn,
            proposal,
            valid_agent_ids=["knowledge", "review", "brain"],
            max_depth=5,
        )
        self.assertEqual(decision.outcome, "ask_user")
        self.assertFalse(decision.allowed)
        stored = self.conn.execute(
            "SELECT objective, data_sensitivity FROM handoff_proposals WHERE id=?",
            (proposal["id"],),
        ).fetchone()
        self.assertEqual(stored["data_sensitivity"], "sensitive")
        self.assertNotIn("API key", stored["objective"])

    def test_authorized_work_is_idempotent_and_ledger_backed(self):
        proposal = self.proposal()
        decision = evaluate_handoff_proposal(
            self.conn,
            proposal,
            valid_agent_ids=["knowledge", "review", "brain"],
            max_depth=5,
        )
        self.assertTrue(decision.allowed)

        args = (
            self.conn,
            "session-1",
            "review",
            0,
            "原始输入",
            "Agent 输出",
            "检查观点",
            [],
        )
        first = save_handoff(*args, agent_a_id="knowledge", proposal_id=proposal["id"])
        second = save_handoff(*args, agent_a_id="knowledge", proposal_id=proposal["id"])
        self.assertEqual(first, second)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM execution_ledger").fetchone()[0],
            1,
        )

        mark_running(self.conn, first)
        mark_done(self.conn, first)
        item = get_by_id(self.conn, first)
        ledger = self.conn.execute(
            "SELECT status FROM execution_ledger WHERE idempotency_key=?",
            (item["idempotency_key"],),
        ).fetchone()
        self.assertEqual(ledger["status"], "succeeded")


class KnowledgePublicationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    async def asyncTearDown(self):
        self.conn.close()

    async def test_agent_note_is_not_rag_visible_until_user_publishes(self):
        tools = build_note_tools(self.conn)
        save_note = next(tool for tool in tools if tool.name == "save_note")
        get_note = next(tool for tool in tools if tool.name == "get_note")
        set_trace_context("trace-a", session_id="session-a", agent_id="knowledge")
        with patch(
            "src.tools.notes._background_embed",
            new=AsyncMock(return_value=None),
        ):
            result = await save_note.ainvoke(
                {
                    "title": "门禁状态机",
                    "content": "Proposal 经过 Policy Gate 才能执行",
                    "tags": "agent,安全",
                }
            )

        import json

        payload = json.loads(result)
        note_id = payload["id"]
        self.assertEqual(payload["knowledge_status"], "pending_review")
        self.assertEqual(
            _fetch_related_notes(self.conn, "门禁状态机"),
            "",
        )
        set_trace_context("trace-b", session_id="session-b", agent_id="knowledge")
        hidden = get_note.invoke({"note_id": note_id})
        self.assertEqual(json.loads(hidden)["status"], "error")

        published = publish_candidate(self.conn, note_id)
        self.assertEqual(published["knowledge_status"], "canonical")
        self.assertIn(
            f"[note:{note_id}]",
            _fetch_related_notes(self.conn, "门禁状态机"),
        )


if __name__ == "__main__":
    unittest.main()
