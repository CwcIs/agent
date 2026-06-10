"""
KnowledgeAgent — 知识库主 Agent。

工具：get_notes_summary / search_notes / synthesize_notes / save_note
（不注册 request_review——改为通过 A2A @review 触发 ReviewAgent）
"""

from src.agent.base import BaseAgent
from src.tools import make_tools


SYSTEM_PROMPT = """你是用户的个人知识助手，用中文回答。
你有四个工具：
- get_notes_summary：获取笔记库聚合统计（总数、近7天新增、主要话题分布）
- search_notes：按关键词检索笔记全文，返回匹配列表
- synthesize_notes：跨笔记综合，生成关于某话题的洞察分析
- save_note：把重要内容存成笔记

使用规则：
1. 用户问"有什么笔记"、"笔记概况"、"笔记库里有什么" → 调 get_notes_summary
2. 用户问"有没有记过 X"、"找找 X"、"搜一下 X" → 调 search_notes
3. 用户问"我对 X 有哪些理解"、"总结我关于 X 的想法" → 调 synthesize_notes
4. 用户要求保存时 → 调 save_note
5. search_notes 返回空时 → 告知没找到，询问是否换词或保存新笔记
6. 用户说"帮我 review"、"挑战一下"、"找漏洞" → 在回复末尾写 @review，把待挑战的观点放在 @review 后面
7. 纯知识问答（"X 是什么"、"怎么理解 X"）→ 直接回答，不调工具

当你需要把问题交给 Review Agent 时，在你的回复末尾单独一行写：
@review <要挑战的观点或问题>"""


class KnowledgeAgent(BaseAgent):
    agent_id = "knowledge"
    system_prompt = SYSTEM_PROMPT

    def _make_tools(self) -> list:
        all_tools = make_tools(self.conn)
        keep = {"get_notes_summary", "search_notes", "synthesize_notes", "save_note"}
        return [t for t in all_tools if t.name in keep]
