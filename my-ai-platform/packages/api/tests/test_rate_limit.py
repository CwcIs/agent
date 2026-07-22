"""Regression tests for the in-memory request rate limiter."""

import ast
from pathlib import Path
import unittest
from unittest.mock import patch


MAIN_PATH = Path(__file__).parents[1] / "src" / "main.py"


def _load_rate_limiter() -> dict:
    """Load only the rate-limiter definitions, avoiding app startup side effects."""
    tree = ast.parse(MAIN_PATH.read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if (
            isinstance(node, (ast.Import, ast.ImportFrom))
            and any(alias.name == "time" for alias in node.names)
        )
        or (
            isinstance(node, (ast.Assign, ast.AnnAssign))
            and any(
                isinstance(target, ast.Name)
                and target.id.startswith("_RATE_LIMIT")
                for target in (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
            )
        )
        or (isinstance(node, ast.FunctionDef) and node.name == "_check_rate_limit")
    ]
    namespace: dict = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), MAIN_PATH, "exec"), namespace)
    namespace["_rate_limit_store"] = {}
    return namespace


class RateLimitTests(unittest.TestCase):
    def test_rejects_after_limit_and_resets_after_window(self):
        namespace = _load_rate_limiter()
        check = namespace["_check_rate_limit"]

        with patch.object(namespace["time"], "monotonic", return_value=100.0):
            for _ in range(namespace["_RATE_LIMIT_MAX"]):
                self.assertTrue(check("client"))
            self.assertFalse(check("client"))

        with patch.object(namespace["time"], "monotonic", return_value=161.0):
            self.assertTrue(check("client"))


if __name__ == "__main__":
    unittest.main()
