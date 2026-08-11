import unittest

from src.agent.runtime_models import (
    append_tool_events,
    merge_agent_results,
    merge_branch_results,
)


class RuntimeReducerTests(unittest.TestCase):
    def test_agent_results_are_idempotent_per_branch_and_agent(self):
        merged = merge_agent_results(
            [{"branch_id": "root", "agent_id": "knowledge", "status": "failed"}],
            [{"branch_id": "root", "agent_id": "knowledge", "status": "completed"}],
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["status"], "completed")

    def test_tool_events_and_branches_are_upserted(self):
        tools = append_tool_events(
            [{"tool_call_id": "call-1", "status": "started"}],
            [{"tool_call_id": "call-1", "status": "completed"}],
        )
        branches = merge_branch_results(
            [{"branch_id": "review-1", "status": "running"}],
            [{"branch_id": "review-1", "status": "completed"}],
        )
        self.assertEqual(tools, [{"tool_call_id": "call-1", "status": "completed"}])
        self.assertEqual(branches, [{"branch_id": "review-1", "status": "completed"}])


if __name__ == "__main__":
    unittest.main()
