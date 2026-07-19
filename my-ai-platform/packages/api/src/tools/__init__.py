"""Agent tool registry grouped by feature domain."""

import sqlite3

from src.tools._shared import TOOL_TIMEOUT, _background_embed
from src.tools.custom import build_custom_tools
from src.tools.imports import build_import_tools
from src.tools.integrations import build_integration_tools
from src.tools.knowledge import build_knowledge_tools
from src.tools.notes import build_note_tools
from src.tools.review import build_review_tools


def make_tools(conn: sqlite3.Connection) -> list:
    """Build the complete tool set for an Agent database connection."""
    tools = []
    for builder in (
        build_note_tools,
        build_knowledge_tools,
        build_import_tools,
        build_review_tools,
        build_integration_tools,
        build_custom_tools,
    ):
        tools.extend(builder(conn))
    return tools


__all__ = ["TOOL_TIMEOUT", "_background_embed", "make_tools"]
