"""
BrainAgent — 联想扩展 Agent（Gemini 驱动）。

工具：search_notes / synthesize_notes（只读笔记库）
不注册 save_note（Brain Agent 只联想，不写入）

角色（MD §4.2）：
  Gemini → 联想扩展、头脑风暴、跨领域连接
"""

from pathlib import Path

from src.agent.base import BaseAgent
from src.tools import make_tools


_PROMPT_PATH = (
    Path(__file__).parent.parent.parent.parent.parent.parent / "prompts/gemini.system.md"
)

_DEFAULT_SYSTEM = """你是一个创造性思维 AI 助手，负责将当前话题连接到其他领域，发现意想不到的关联，用中文回答。

你有两个工具：
- search_notes：搜索用户笔记库，找相关的历史想法
- synthesize_notes：跨笔记综合，生成关于某话题的洞察

使用规则：
1. 用户提到一个话题 → 先用 search_notes 看用户有没有记过相关内容
2. 如果找到多个相关笔记 → 用 synthesize_notes 做跨领域综合
3. 联想时标注灵感来源（来自哪条笔记 或 哪个外部领域）
4. 标注每个联想的"跳跃距离"（1-5，1=直接相关，5=完全跨界）
5. 不评判想法的"好坏"，只提供可能性
6. 当联想完成后，如果觉得需要挑战验证 → 在回复末尾写 @review <待挑战的观点>

核心能力：
- 联想扩展：从当前讨论扩展到相关领域（产品、技术、商业、心理学等）
- 头脑风暴：提出多种可能方向，不预设对错
- 跨领域连接：找到表面无关但底层相似的模式"""


def _load_system() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return _DEFAULT_SYSTEM


class BrainAgent(BaseAgent):
    agent_id = "brain"
    system_prompt = _load_system()

    def _make_tools(self) -> list:
        all_tools = make_tools(self.conn)
        keep = {"search_notes", "synthesize_notes"}
        return [t for t in all_tools if t.name in keep]
