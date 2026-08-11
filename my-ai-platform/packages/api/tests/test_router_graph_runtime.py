import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent.router_graph_runtime import route_graph_stream
from src.db.schema import init_db


class FakeAgent:
    def __init__(self, agent_id: str, output: str, error: str = ""):
        self.agent_id = agent_id
        self.output = output
        self.error = error

    def set_runtime_context(self, *args, **kwargs):
        return None

    async def astream(self, messages, config):
        if self.error:
            raise RuntimeError(self.error)
        yield {"type": "token", "agentId": self.agent_id, "delta": self.output}
        yield {"type": "done", "agentId": self.agent_id}


class RouterGraphRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.checkpoint_path = Path(self.temp_dir.name) / "checkpoint.db"

    async def asyncTearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    async def collect(self, agents):
        with (
            patch("src.agent.router_graph_runtime.get_agent", side_effect=agents.get),
            patch(
                "src.agent.router_graph_runtime.list_agent_ids",
                return_value=["knowledge", "review", "brain"],
            ),
        ):
            return [
                event
                async for event in route_graph_stream(
                    "分析这个观点",
                    "session-graph",
                    self.conn,
                    trace_id="run-graph",
                    checkpoint_path=self.checkpoint_path,
                )
            ]

    async def test_single_agent_run_persists_ordered_events(self):
        events = await self.collect(
            {"knowledge": FakeAgent("knowledge", "综上所述，这是完整结论。")}
        )
        self.assertEqual(events[-1]["type"], "done")
        run = self.conn.execute(
            "SELECT status, final_verdict FROM agent_runs WHERE id='run-graph'"
        ).fetchone()
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["final_verdict"], "natural_end")

    async def test_serial_handoff_runs_only_after_governance(self):
        events = await self.collect(
            {
                "knowledge": FakeAgent("knowledge", "初步判断。\n@review 检查逻辑"),
                "review": FakeAgent("review", "综上所述，需要补充一个边界条件。"),
            }
        )
        switches = [event for event in events if event["type"] == "agent_switch"]
        self.assertEqual([event["agentId"] for event in switches], ["review"])
        decision = self.conn.execute(
            "SELECT outcome FROM policy_decisions"
        ).fetchone()
        self.assertEqual(decision["outcome"], "allow")
        event_types = [
            row[0]
            for row in self.conn.execute(
                "SELECT event_type FROM run_events ORDER BY sequence"
            ).fetchall()
        ]
        self.assertLess(
            event_types.index("handoff.approved"),
            event_types.index("agent.started", event_types.index("agent.started") + 1),
        )

    async def test_parallel_handoff_joins_when_one_branch_fails(self):
        events = await self.collect(
            {
                "knowledge": FakeAgent(
                    "knowledge",
                    "初步判断。\n@review 检查逻辑\n@brain 扩展关联",
                ),
                "review": FakeAgent("review", "Review 完成。"),
                "brain": FakeAgent("brain", "", error="provider unavailable"),
            }
        )
        self.assertEqual(events[-1]["type"], "done")
        run = self.conn.execute(
            "SELECT status, final_verdict FROM agent_runs WHERE id='run-graph'"
        ).fetchone()
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["final_verdict"], "branches_joined")
        statuses = [
            row[0]
            for row in self.conn.execute(
                "SELECT status FROM execution_ledger ORDER BY created_at"
            ).fetchall()
        ]
        self.assertCountEqual(statuses, ["succeeded", "failed"])

    async def test_sensitive_handoff_interrupts_then_resumes_after_approval(self):
        agents = {
            "knowledge": FakeAgent(
                "knowledge",
                "需要进一步检查。\n@review 检查这段包含 API key 的内容",
            ),
            "review": FakeAgent("review", "综上所述，敏感内容检查完成。"),
        }
        initial_events = await self.collect(agents)
        self.assertEqual(
            initial_events[-1]["type"], "approval_required", initial_events
        )
        run = self.conn.execute(
            "SELECT status FROM agent_runs WHERE id='run-graph'"
        ).fetchone()
        self.assertEqual(run["status"], "waiting_approval")

        from src.agent.router_graph_runtime import resume_graph_stream

        with (
            patch("src.agent.router_graph_runtime.get_agent", side_effect=agents.get),
            patch(
                "src.agent.router_graph_runtime.list_agent_ids",
                return_value=["knowledge", "review", "brain"],
            ),
        ):
            resumed_events = [
                event
                async for event in resume_graph_stream(
                    "run-graph",
                    {"approved": True},
                    self.conn,
                    checkpoint_path=self.checkpoint_path,
                )
            ]
        self.assertIn("approval_resolved", [event["type"] for event in resumed_events])
        self.assertEqual(resumed_events[-1]["type"], "done")
        approval = self.conn.execute(
            "SELECT status FROM approval_requests"
        ).fetchone()
        self.assertEqual(approval["status"], "approved")

    async def test_rejected_approval_completes_without_target_execution(self):
        agents = {
            "knowledge": FakeAgent(
                "knowledge",
                "需要进一步检查。\n@review 检查这段包含密码的内容",
            ),
            "review": FakeAgent("review", "不应执行"),
        }
        await self.collect(agents)
        from src.agent.router_graph_runtime import resume_graph_stream

        with (
            patch("src.agent.router_graph_runtime.get_agent", side_effect=agents.get),
            patch(
                "src.agent.router_graph_runtime.list_agent_ids",
                return_value=["knowledge", "review", "brain"],
            ),
        ):
            events = [
                event
                async for event in resume_graph_stream(
                    "run-graph",
                    {"approved": False},
                    self.conn,
                    checkpoint_path=self.checkpoint_path,
                )
            ]
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM execution_ledger").fetchone()[0],
            0,
        )


if __name__ == "__main__":
    unittest.main()
