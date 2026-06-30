"""
BaseAgent — 所有 Agent 的抽象基类。

每个 Agent 持有：
- agent_id: str            唯一标识，对应 @mention 中的名字
- system_prompt: str       该 Agent 的专属 prompt
- tools: list              该 Agent 按需注册的工具

astream(messages, config) → AsyncGenerator[dict, None]
  产出格式：{"type": "token"|"tool_start"|"tool_end"|"done", ...agentId 已注入}
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator
import sqlite3

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict, Annotated

from src.agent.providers import resolve_model


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


class BaseAgent(ABC):
    agent_id: str
    system_prompt: str

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._session_id = ""
        self._prompt_version = "v1"
        self._trace_id = ""
        self._tools = self._make_tools()
        self._graph = self._build_graph()

    def set_runtime_context(self, session_id: str, prompt_version: str = "v1", trace_id: str = "") -> None:
        """设置当前请求的运行时上下文，call_llm 需要这些来记账和预算检查。"""
        self._session_id = session_id
        self._prompt_version = prompt_version
        self._trace_id = trace_id

    @abstractmethod
    def _make_tools(self) -> list:
        """子类返回该 Agent 专属工具列表。"""

    def _build_graph(self):
        tools = self._tools
        # Phase 2: 按 agent_id 选择模型（review → GPT, knowledge → DeepSeek）
        llm = resolve_model(self.agent_id, tools if tools else None)
        system = self.system_prompt

        async def call_model(state: AgentState) -> dict:
            from src.lib.llm_call import call_llm
            msgs = [SystemMessage(content=system)] + state["messages"]
            response = await call_llm(
                llm, msgs,
                conn=self.conn,
                session_id=self._session_id,
                prompt_version=self._prompt_version,
                trace_id=self._trace_id,
                agent_id=self.agent_id,
            )
            return {"messages": [response]}

        def should_continue(state: AgentState) -> str:
            last = state["messages"][-1]
            return "tools" if getattr(last, "tool_calls", None) else END

        builder = StateGraph(AgentState)
        builder.add_node("call_model", call_model)
        builder.set_entry_point("call_model")

        if tools:
            builder.add_node("tools", ToolNode(tools))
            builder.add_conditional_edges("call_model", should_continue)
            builder.add_edge("tools", "call_model")
        else:
            builder.add_edge("call_model", END)

        return builder.compile()

    async def astream(
        self,
        messages: list[BaseMessage],
        config: dict,
    ) -> AsyncGenerator[dict, None]:
        """
        流式运行该 Agent，产出带 agentId 的 SSE-ready 事件。
        """
        import json as _json

        async for event in self._graph.astream_events(
            {"messages": messages},
            config=config,
            version="v2",
        ):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    yield {"type": "token", "agentId": self.agent_id, "delta": chunk.content}

            elif kind == "on_tool_start":
                yield {
                    "type": "tool_start",
                    "agentId": self.agent_id,
                    "name": event["name"],
                    "input": event["data"].get("input", {}),
                }

            elif kind == "on_tool_end":
                output = event["data"].get("output", "")
                yield {
                    "type": "tool_end",
                    "agentId": self.agent_id,
                    "name": event["name"],
                    "result": str(output)[:300],
                }

        yield {"type": "done", "agentId": self.agent_id}
