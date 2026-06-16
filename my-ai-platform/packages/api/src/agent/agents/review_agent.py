"""
ReviewAgent — 思维挑战者 Agent。

工具：search_notes（可访问笔记库，提供有据可查的反例）
不注册 save_note（Review Agent 只挑战，不写入）
"""

from pathlib import Path

from src.agent.base import BaseAgent
from src.tools import make_tools


_PROMPT_PATH = (
    Path(__file__).parent.parent.parent.parent.parent.parent / "prompts/review.system.md"
)

_DEFAULT_SYSTEM = """你是一个严格的思维挑战者，用中文回答。
你的任务是从三个角度挑战用户的观点：
1. 逻辑漏洞 — 前提不成立或推理跳跃的地方
2. 遗漏假设 — 作者默认了但没有说出来的前提
3. 反例 — 能推翻或限制结论的具体案例

你有两个工具：
- search_notes：从用户的笔记库里找反例或佐证
- get_note：按 ID 读取一条笔记的完整内容

如果搜到的笔记里有与当前观点矛盾的内容，请明确引用。

挑战结束后，给出 1-2 个追问，帮用户深化思考。
语气：直接、清晰，不客气，但不要嘲讽。"""


def _load_system() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return _DEFAULT_SYSTEM


class ReviewAgent(BaseAgent):
    agent_id = "review"
    system_prompt = _load_system()

    def _make_tools(self) -> list:
        all_tools = make_tools(self.conn)
        keep = {"search_notes", "get_note"}
        return [t for t in all_tools if t.name in keep]
