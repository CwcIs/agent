"""
Review Agent — 思维挑战者
接收一段观点文本，返回逻辑漏洞 / 遗漏假设 / 反例 + 追问。
prompt-chaining 实现，不是真正 A2A，但行为上等价。
"""

from pathlib import Path
from langchain_core.messages import HumanMessage, SystemMessage

_PROMPT_PATH = Path(__file__).parent.parent.parent.parent.parent.parent / "prompts/review.system.md"

def _load_system_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return "你是一个严格的思维挑战者，找出用户观点的逻辑漏洞、遗漏假设和反例。用中文回答。"


async def run_review(content: str) -> str:
    """对 content 里的观点运行 Review Agent，返回挑战文本。"""
    from src.agent.providers.deepseek import make_deepseek
    llm = make_deepseek()
    system = _load_system_prompt()
    resp = await llm.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=f"请挑战以下观点：\n\n{content}"),
    ])
    return resp.content
