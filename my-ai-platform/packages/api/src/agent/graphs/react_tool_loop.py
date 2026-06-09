# ============================================================
# ReAct Tool Loop — LangGraph StateGraph 实现
# 对应 MD §3.3 — 单 Cat 内 Thought → Action → Observation 循环
#
# 这是整个平台 Agent 原理的核心，Phase 1 必须跑通。
# 没有 tool loop 跑通，Phase 1 验收不算过。
#
# 图结构（LangGraph StateGraph）：
#   __start__
#       │
#       ▼
#   [call_model]  ←──────────────┐
#       │                        │
#       ▼                        │
#   should_continue?             │
#   has tool_calls?              │
#       │                        │
#   ┌───┴───┐                    │
#   │ YES   │ NO                 │
#   ▼       ▼                    │
# [tools]  END                   │
#   │                            │
#   └────────────────────────────┘
#
# 对应 MD §8.6 的伪代码 runReActLoop()，LangGraph 把它画成了图：
#   - StateGraph 节点 = [stream] → [check_tool_use] → [run_tools] → 回到 [stream]
#   - 条件边 = should_continue 判断最后一条消息是否有 tool_calls
#   - MAX_TOOL_LOOP_ITERATIONS 通过 LangGraph recursion_limit 控制
#
# Phase 1 验收（MD §8.3 Agent 原理）：
#   注册两个工具 searchNotes + saveNote，给 Claude 一句需要两跳的话：
#   "把我刚说的'B 端优先'整理成笔记，但先看看我之前对 B 端有没有写过什么。"
#   期待 chunk 序列：
#     tool_use(searchNotes) → tool_result → text("找到 3 条...")
#     → tool_use(saveNote) → tool_result → text("已保存")
#   这串序列出现一次，"我懂 Agent 是怎么自己干活的"才算落地。
# ============================================================

import sqlite3
from typing import Annotated

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from src.agent.providers.deepseek import make_deepseek
from src.tools import make_tools

# MAX_TOOL_LOOP_ITERATIONS = 10（MD §3.5）
# LangGraph 用 recursion_limit 控制，传给 compile() 的 config
MAX_ITERATIONS = 10

SYSTEM_PROMPT = """你是用户的个人知识助手，用中文回答。
你有三个工具：
- get_notes_summary：获取笔记库聚合统计（总数、近7天新增、主要话题分布）
- search_notes：按关键词检索笔记全文
- save_note：把重要内容存成笔记

使用规则：
1. 用户问"有什么笔记"、"笔记概况"、"笔记库里有什么"→ 先调 get_notes_summary，返回统计摘要，让用户决定下一步查什么
2. 用户指定关键词或话题时 → 调 search_notes 精确检索
3. search_notes 返回空结果时 → 告诉用户没有找到相关笔记，主动询问：是否换个关键词，或者要把当前话题保存成新笔记
4. 用户要求保存时 → 调 save_note"""


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_graph(
    conn: sqlite3.Connection,
    checkpointer: AsyncSqliteSaver,
):
    """
    构建 ReAct 图并编译。
    conn         — 业务 DB 连接（tools 用）
    checkpointer — AsyncSqliteSaver（多轮对话持久化）
    """
    tools = make_tools(conn)
    llm = make_deepseek(tools)

    async def call_model(state: AgentState) -> dict:
        msgs = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = await llm.ainvoke(msgs)
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = (
        StateGraph(AgentState)
        .add_node("call_model", call_model)
        .add_node("tools", ToolNode(tools))
        .set_entry_point("call_model")
        .add_conditional_edges("call_model", should_continue)
        .add_edge("tools", "call_model")
        .compile(
            checkpointer=checkpointer,
            # recursion_limit 限制最大循环轮数，防止死循环
        )
    )
    return graph
