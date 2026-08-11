"""Shared state and result contracts for the hierarchical router runtime."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict


def _upsert(items: list[dict], updates: list[dict], keys: tuple[str, ...]) -> list[dict]:
    merged = {tuple(item.get(key, "") for key in keys): item for item in items}
    for update in updates:
        identity = tuple(update.get(key, "") for key in keys)
        merged[identity] = {**merged.get(identity, {}), **update}
    return list(merged.values())


def merge_agent_results(left: list[dict], right: list[dict]) -> list[dict]:
    return _upsert(left, right, ("branch_id", "agent_id"))


def append_tool_events(left: list[dict], right: list[dict]) -> list[dict]:
    return _upsert(left, right, ("tool_call_id",))


def merge_branch_results(left: list[dict], right: list[dict]) -> list[dict]:
    return _upsert(left, right, ("branch_id",))


class AgentResult(TypedDict):
    agent_id: str
    branch_id: str
    output: str
    tool_events: list[dict[str, Any]]
    handoff_text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    status: Literal["completed", "failed", "cancelled"]


class HandoffProposal(TypedDict):
    proposal_id: str
    source_agent: str
    target_agent: str
    intent: str
    payload: str
    reason: str
    requested_capabilities: list[str]
    estimated_tokens: int
    side_effects: list[str]
    depth: int
    source_output_id: str


class RouterState(TypedDict):
    run_id: str
    session_id: str
    user_message_id: str
    prompt_version: str
    user_input: str
    context_messages: list[BaseMessage]
    related_note_ids: list[str]
    current_agent: str
    current_branch_id: str
    depth: int
    turn_count: int
    agent_results: Annotated[list[AgentResult], merge_agent_results]
    tool_events: Annotated[list[dict[str, Any]], append_tool_events]
    proposals: list[HandoffProposal]
    decisions: list[dict[str, Any]]
    dispatch_plan: dict[str, Any] | None
    branch_results: Annotated[list[dict[str, Any]], merge_branch_results]
    pending_approval: dict[str, Any] | None
    verdict: str
    final_output: str
    error: dict[str, Any] | None
