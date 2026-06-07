# LangGraph 图 — barrel export
#
# 对应 MD 附录 Mermaid 图：
#   图 2 — ReAct Tool Loop（react_tool_loop.py）
#   图 3 — Prompt-Chained Orchestration（a2a_orchestration.py）
#   图 5 — 场景 A 数据流（capture_note.py）
#   场景 D 数据流（daily_digest.py）
#   场景 C 数据流（idea_collision.py）

from .react_tool_loop import build_react_tool_loop
from .a2a_orchestration import build_a2a_orchestration, parse_a2a_mentions
from .capture_note import build_capture_note_graph
from .daily_digest import build_daily_digest_graph
from .idea_collision import build_idea_collision_graph
