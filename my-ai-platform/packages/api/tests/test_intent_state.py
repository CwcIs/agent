import unittest

from src.context.intent import build_intent_state, format_intent_context


class IntentStateTests(unittest.TestCase):
    def test_goal_defaults_to_user_input_and_files_are_normalized(self):
        intent = build_intent_state(
            "整理架构方案",
            referenced_files=[{"path": "docs/plan.md", "status": "processed"}],
        )
        self.assertEqual(intent["current_goal"], "整理架构方案")
        self.assertEqual(intent["referenced_files"][0]["name"], "plan.md")
        self.assertIn("plan.md [processed]", format_intent_context(intent))

    def test_invalid_statuses_fall_back_safely(self):
        intent = build_intent_state(
            "继续",
            task_status="unknown",
            referenced_files=[{"name": "draft", "status": "unknown"}],
        )
        self.assertEqual(intent["task_status"], "active")
        self.assertEqual(intent["referenced_files"][0]["status"], "available")


if __name__ == "__main__":
    unittest.main()
