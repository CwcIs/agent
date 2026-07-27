import sqlite3
import unittest
from unittest.mock import patch

from src.agent.router import route_serial
from src.db.schema import init_db


class FakeAgent:
    def __init__(self, agent_id: str, output: str):
        self.agent_id = agent_id
        self.output = output

    def set_runtime_context(self, *args, **kwargs):
        return None

    async def astream(self, messages, config):
        yield {"type": "token", "agentId": self.agent_id, "delta": self.output}
        yield {"type": "done", "agentId": self.agent_id}


class RouterGovernanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    async def asyncTearDown(self):
        self.conn.close()

    async def collect(self, agents: dict[str, FakeAgent]):
        with (
            patch("src.agent.router.get_agent", side_effect=agents.get),
            patch(
                "src.agent.router.list_agent_ids",
                return_value=["knowledge", "review", "brain"],
            ),
        ):
            return [
                event
                async for event in route_serial(
                    "请分析这个观点",
                    "session-gate",
                    conn=self.conn,
                    trace_id="trace-gate",
                )
            ]

    async def test_explicit_mention_requires_policy_before_execution(self):
        events = await self.collect(
            {
                "knowledge": FakeAgent(
                    "knowledge",
                    "我先整理了观点。\n@review 检查其中的逻辑漏洞",
                ),
                "review": FakeAgent(
                    "review",
                    "存在一个遗漏假设。综上所述，需要补充边界条件。",
                ),
            }
        )

        switches = [
            event["agentId"]
            for event in events
            if event["type"] == "agent_switch"
        ]
        self.assertIn("review", switches)
        proposal = self.conn.execute(
            "SELECT status FROM handoff_proposals WHERE trigger_type='explicit'"
        ).fetchone()
        self.assertEqual(proposal["status"], "executed")
        decision = self.conn.execute(
            "SELECT outcome FROM policy_decisions"
        ).fetchone()
        self.assertEqual(decision["outcome"], "allow")
        ledger = self.conn.execute(
            "SELECT status FROM execution_ledger"
        ).fetchone()
        self.assertEqual(ledger["status"], "succeeded")

    async def test_shadow_mention_is_recorded_but_never_executed(self):
        events = await self.collect(
            {
                "knowledge": FakeAgent(
                    "knowledge",
                    "这是一段已经完成的分析，请 @review 检查其中逻辑。"
                    "这里继续补足结论，使回复长度足够并自然结束。综上所述，分析完成。",
                ),
                "review": FakeAgent("review", "不应被执行"),
            }
        )

        switches = [
            event
            for event in events
            if event["type"] == "agent_switch" and event["agentId"] == "review"
        ]
        self.assertEqual(switches, [])
        proposal = self.conn.execute(
            """SELECT status, trigger_type FROM handoff_proposals
               WHERE trigger_type='shadow'"""
        ).fetchone()
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal["status"], "degrade")
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM worklist").fetchone()[0],
            0,
        )


if __name__ == "__main__":
    unittest.main()
