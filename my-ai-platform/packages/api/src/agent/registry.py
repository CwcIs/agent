"""
AgentRegistry — Agent 单例注册表。

main.py 启动时调用 init_registry(conn) 注册所有 Agent。
路由层通过 get_agent(agent_id) 获取实例。
"""

import sqlite3
from typing import Optional

from src.agent.base import BaseAgent

_registry: dict[str, BaseAgent] = {}
_default_agent_id: str = "knowledge"


def init_registry(conn: sqlite3.Connection) -> None:
    from src.agent.agents.knowledge_agent import KnowledgeAgent
    from src.agent.agents.review_agent import ReviewAgent
    from src.agent.agents.brain_agent import BrainAgent

    global _registry
    _registry = {
        "knowledge": KnowledgeAgent(conn),
        "review": ReviewAgent(conn),
        "brain": BrainAgent(conn),
    }


def get_agent(agent_id: str) -> Optional[BaseAgent]:
    return _registry.get(agent_id)


def get_default_agent() -> BaseAgent:
    return _registry[_default_agent_id]


def list_agent_ids() -> list[str]:
    return list(_registry.keys())
