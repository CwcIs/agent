"""Hierarchical Router Graph runtime with Agent ReAct subgraphs."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command
from typing_extensions import TypedDict

from src.agent.governance import (
    create_handoff_proposal,
    ensure_execution,
    evaluate_handoff_proposal,
    mark_execution,
)
from src.agent.registry import get_agent, list_agent_ids
from src.agent.router_parser import parse_a2a_mentions, parse_user_tags
from src.agent.run_events import append_run_event, create_run
from src.agent.verdict import detect_verdict
from src.context.assemble import agent_display_name, assemble_context, package_handoff

MAX_A2A_DEPTH = 5
MAX_AGENT_TURNS = 10
CHECKPOINT_DB = Path(__file__).parent.parent.parent / "data" / "checkpoint.db"
_active_sink: ContextVar[Callable[[dict[str, Any]], None] | None] = ContextVar(
    "router_graph_event_sink", default=None
)


class GraphRuntimeState(TypedDict):
    run_id: str
    session_id: str
    user_message_id: str
    prompt_version: str
    user_input: str
    cleaned_input: str
    current_agent: str
    current_branch_id: str
    depth: int
    turn_count: int
    active_messages: list
    current_output: str
    current_tool_events: list[dict[str, Any]]
    agent_results: list[dict[str, Any]]
    proposals: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    approved_proposals: list[dict[str, Any]]
    branch_results: list[dict[str, Any]]
    pending_approval: dict[str, Any] | None
    verdict: str
    final_output: str
    error: dict[str, Any] | None


def _save_message(
    conn: sqlite3.Connection,
    *,
    message_id: str,
    session_id: str,
    agent_id: str,
    role: str,
    content: str,
) -> None:
    conn.execute(
        """INSERT INTO messages (id, session_id, agent_id, role, content)
           VALUES (?, ?, ?, ?, ?)""",
        (message_id, session_id, agent_id, role, content),
    )
    conn.commit()


def _emit(
    conn: sqlite3.Connection,
    state: GraphRuntimeState,
    event_type: str,
    *,
    legacy_event: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    node_name: str = "",
    agent_id: str = "",
) -> dict[str, Any]:
    envelope = append_run_event(
        conn,
        run_id=state["run_id"],
        branch_id=state.get("current_branch_id", ""),
        event_type=event_type,
        data=data or {},
        node_name=node_name,
        agent_id=agent_id,
    )
    sink = _active_sink.get()
    if sink is not None:
        sink({"envelope": envelope, "legacy": legacy_event})
    return envelope


def build_router_graph(
    conn: sqlite3.Connection,
    checkpointer: AsyncSqliteSaver | None = None,
):
    async def accept_input(state: GraphRuntimeState) -> dict:
        tag_agent, cleaned_input = parse_user_tags(state["user_input"])
        _save_message(
            conn,
            message_id=state["user_message_id"],
            session_id=state["session_id"],
            agent_id="user",
            role="user",
            content=state["user_input"],
        )
        conn.execute(
            "UPDATE agent_runs SET status='running', current_node='accept_input' WHERE id=?",
            (state["run_id"],),
        )
        conn.commit()
        _emit(
            conn,
            state,
            "run.started",
            data={"prompt_version": state["prompt_version"]},
            node_name="accept_input",
        )
        return {"cleaned_input": cleaned_input, "current_agent": tag_agent or "knowledge"}

    async def assemble_context_node(state: GraphRuntimeState) -> dict:
        history = assemble_context(
            conn,
            state["session_id"],
            user_input=state["cleaned_input"],
        )
        messages = history + [HumanMessage(content=state["cleaned_input"])]
        _emit(
            conn,
            state,
            "node.completed",
            data={"message_count": len(messages)},
            node_name="assemble_context",
        )
        return {"active_messages": messages}

    async def select_agent(state: GraphRuntimeState) -> dict:
        if get_agent(state["current_agent"]) is None:
            return {
                "error": {"code": "unknown_agent", "agent_id": state["current_agent"]},
                "verdict": "unknown_agent",
            }
        _emit(
            conn,
            state,
            "node.completed",
            data={"selected_agent": state["current_agent"]},
            node_name="select_agent",
            agent_id=state["current_agent"],
        )
        return {}

    async def execute_agent(state: GraphRuntimeState) -> dict:
        agent_id = state["current_agent"]
        agent = get_agent(agent_id)
        if agent is None:
            return {"error": {"code": "unknown_agent"}, "verdict": "unknown_agent"}
        phase_trace_id = str(uuid.uuid4())
        agent.set_runtime_context(
            state["session_id"],
            state["prompt_version"],
            phase_trace_id,
            root_trace_id=state["run_id"],
        )
        switch_event = {
            "type": "agent_switch",
            "agentId": agent_id,
            "trace_id": phase_trace_id,
        }
        _emit(
            conn,
            state,
            "agent.started",
            legacy_event=switch_event if state["turn_count"] > 0 else None,
            data={"depth": state["depth"], "turn": state["turn_count"] + 1},
            node_name="execute_agent",
            agent_id=agent_id,
        )
        output = ""
        tool_events: list[dict[str, Any]] = []
        config = {
            "configurable": {
                "thread_id": f'{state["session_id"]}:{state["run_id"]}:{agent_id}:{state["depth"]}'
            },
            "recursion_limit": MAX_AGENT_TURNS,
        }
        try:
            async for event in agent.astream(state["active_messages"], config):
                event_type = event.get("type")
                if event_type == "token":
                    output += event.get("delta", "")
                    _emit(
                        conn,
                        state,
                        "agent.delta",
                        legacy_event=event,
                        data={"agent_id": agent_id, "delta": event.get("delta", "")},
                        node_name="execute_agent",
                        agent_id=agent_id,
                    )
                elif event_type in {"tool_start", "tool_end"}:
                    tool_events.append(event)
                    normalized = "tool.started" if event_type == "tool_start" else "tool.completed"
                    _emit(
                        conn,
                        state,
                        normalized,
                        legacy_event=event,
                        data={key: value for key, value in event.items() if key != "type"},
                        node_name="execute_agent",
                        agent_id=agent_id,
                    )
        except Exception as exc:
            _emit(
                conn,
                state,
                "agent.failed",
                legacy_event={"type": "error", "agentId": agent_id, "message": str(exc)},
                data={"message": str(exc)},
                node_name="execute_agent",
                agent_id=agent_id,
            )
            return {
                "error": {"code": "agent_failed", "message": str(exc)},
                "verdict": "agent_error",
            }

        result = {
            "agent_id": agent_id,
            "branch_id": state["current_branch_id"],
            "output": output,
            "tool_events": tool_events,
            "handoff_text": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "status": "completed",
        }
        _save_message(
            conn,
            message_id=str(uuid.uuid4()),
            session_id=state["session_id"],
            agent_id=agent_id,
            role="assistant",
            content=output,
        )
        _emit(
            conn,
            state,
            "agent.completed",
            data={"output_chars": len(output)},
            node_name="execute_agent",
            agent_id=agent_id,
        )
        return {
            "current_output": output,
            "current_tool_events": tool_events,
            "agent_results": state["agent_results"] + [result],
            "turn_count": state["turn_count"] + 1,
        }

    async def parse_proposals(state: GraphRuntimeState) -> dict:
        proposals: list[dict[str, Any]] = []
        for target_agent, payload in parse_a2a_mentions(
            state["current_output"], state["current_agent"], list_agent_ids()
        ):
            proposal = create_handoff_proposal(
                conn,
                trace_id=state["run_id"],
                phase_trace_id="",
                session_id=state["session_id"],
                source_agent_id=state["current_agent"],
                target_agent_id=target_agent,
                objective=payload,
                depth=state["depth"],
                input_refs=[f'run:{state["run_id"]}'],
            )
            proposals.append(proposal)
            _emit(
                conn,
                state,
                "handoff.proposed",
                data={"proposal_id": proposal["id"], "target_agent": target_agent},
                node_name="parse_proposals",
                agent_id=state["current_agent"],
            )
        return {"proposals": proposals}

    async def govern(state: GraphRuntimeState) -> dict:
        decisions = []
        approved = []
        pending_approval = None
        for proposal in state["proposals"]:
            decision = evaluate_handoff_proposal(
                conn,
                proposal,
                valid_agent_ids=list_agent_ids(),
                max_depth=MAX_A2A_DEPTH,
            )
            decision_data = {
                "proposal_id": proposal["id"],
                "outcome": decision.outcome,
                "reason": decision.reason,
            }
            decisions.append(decision_data)
            if decision.allowed:
                approved.append(proposal)
            elif decision.outcome == "ask_user" and pending_approval is None:
                approval_id = str(uuid.uuid4())
                pending_approval = {
                    "approval_id": approval_id,
                    "proposal_id": proposal["id"],
                    "target_agent": proposal["target_agent_id"],
                    "risk": decision.effective_risk,
                    "reason": decision.reason,
                }
                conn.execute(
                    """INSERT INTO approval_requests
                       (id, run_id, proposal_id, risk, reason)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        approval_id,
                        state["run_id"],
                        proposal["id"],
                        decision.effective_risk,
                        decision.reason,
                    ),
                )
                conn.execute(
                    """UPDATE agent_runs
                       SET status='waiting_approval', current_node='approval_wait'
                       WHERE id=?""",
                    (state["run_id"],),
                )
                conn.commit()
            _emit(
                conn,
                state,
                "handoff.approved" if decision.allowed else "handoff.rejected",
                data=decision_data,
                node_name="govern",
                agent_id=proposal["target_agent_id"],
            )

        mentions = [
            (proposal["target_agent_id"], proposal["objective"])
            for proposal in approved
        ]
        verdict = detect_verdict(
            state["current_output"],
            mentions,
            state["current_agent"],
            state["depth"],
            MAX_A2A_DEPTH,
        )
        if verdict.warning:
            _emit(
                conn,
                state,
                "node.failed" if verdict.reason == "loop_detected" else "node.completed",
                legacy_event={
                    "type": "warning",
                    "agentId": state["current_agent"],
                    "message": verdict.warning,
                },
                data={"reason": verdict.reason, "warning": verdict.warning},
                node_name="verdict",
                agent_id=state["current_agent"],
            )
        return {
            "decisions": state["decisions"] + decisions,
            "approved_proposals": approved,
            "pending_approval": pending_approval,
            "verdict": verdict.reason,
        }

    def route_after_govern(state: GraphRuntimeState) -> str:
        if state.get("pending_approval"):
            return "approval_wait"
        if state.get("error") or not state["approved_proposals"]:
            return "compose_final"
        if len(state["approved_proposals"]) > 1:
            return "parallel_dispatch"
        return "serial_dispatch"

    async def approval_wait(state: GraphRuntimeState) -> dict:
        approval = state["pending_approval"]
        if approval is None:
            return {}
        _emit(
            conn,
            state,
            "approval.required",
            legacy_event={
                "type": "approval_required",
                "agentId": "router",
                "run_id": state["run_id"],
                **approval,
            },
            data=approval,
            node_name="approval_wait",
        )
        return {}

    def route_after_approval(state: GraphRuntimeState) -> str:
        if state.get("pending_approval"):
            return END
        if not state["approved_proposals"]:
            return "compose_final"
        if len(state["approved_proposals"]) > 1:
            return "parallel_dispatch"
        return "serial_dispatch"

    async def serial_dispatch(state: GraphRuntimeState) -> dict:
        proposal = state["approved_proposals"][0]
        _, idempotency_key, execution_status = ensure_execution(
            conn,
            proposal_id=proposal["id"],
            action_type="agent_handoff",
            actor_id="router_graph",
            request_payload={"target_agent": proposal["target_agent_id"]},
        )
        if execution_status == "succeeded":
            return {"approved_proposals": [], "verdict": "duplicate_handoff_skipped"}
        mark_execution(conn, idempotency_key, "running")
        messages = package_handoff(
            original_user_input=state["user_input"],
            agent_a_full_output=state["current_output"],
            mention_content=proposal["objective"],
            tool_events=state["current_tool_events"],
            agent_a_name=agent_display_name(state["current_agent"]),
        )
        mark_execution(
            conn,
            idempotency_key,
            "succeeded",
            result={"target_agent": proposal["target_agent_id"]},
        )
        conn.execute(
            "UPDATE handoff_proposals SET status='executed' WHERE id=?",
            (proposal["id"],),
        )
        conn.commit()
        return {
            "current_agent": proposal["target_agent_id"],
            "current_branch_id": str(uuid.uuid4()),
            "active_messages": messages,
            "depth": state["depth"] + 1,
            "proposals": [],
            "approved_proposals": [],
        }

    async def parallel_dispatch(state: GraphRuntimeState) -> dict:
        source_agent = state["current_agent"]

        async def run_branch(proposal: dict[str, Any]) -> dict[str, Any]:
            target_agent = proposal["target_agent_id"]
            branch_id = str(uuid.uuid4())
            branch_state = {**state, "current_branch_id": branch_id}
            agent = get_agent(target_agent)
            _emit(
                conn,
                branch_state,
                "branch.started",
                legacy_event={
                    "type": "agent_switch",
                    "agentId": target_agent,
                    "trace_id": branch_id,
                },
                data={"source_agent": source_agent, "target_agent": target_agent},
                node_name="parallel_dispatch",
                agent_id=target_agent,
            )
            if agent is None:
                _emit(
                    conn,
                    branch_state,
                    "branch.failed",
                    data={"reason": "unknown_agent"},
                    node_name="parallel_dispatch",
                    agent_id=target_agent,
                )
                return {
                    "branch_id": branch_id,
                    "agent_id": target_agent,
                    "status": "failed",
                    "output": "",
                    "error": "unknown_agent",
                }

            _, idempotency_key, execution_status = ensure_execution(
                conn,
                proposal_id=proposal["id"],
                action_type="agent_handoff",
                actor_id="router_graph",
                request_payload={"target_agent": target_agent, "branch_id": branch_id},
            )
            if execution_status == "succeeded":
                return {
                    "branch_id": branch_id,
                    "agent_id": target_agent,
                    "status": "completed",
                    "output": "",
                    "error": "duplicate_handoff_skipped",
                }
            mark_execution(conn, idempotency_key, "running")
            messages = package_handoff(
                original_user_input=state["user_input"],
                agent_a_full_output=state["current_output"],
                mention_content=proposal["objective"],
                tool_events=state["current_tool_events"],
                agent_a_name=agent_display_name(source_agent),
            )
            agent.set_runtime_context(
                state["session_id"],
                state["prompt_version"],
                branch_id,
                root_trace_id=state["run_id"],
            )
            output = ""
            try:
                async for event in agent.astream(
                    messages,
                    {
                        "configurable": {
                            "thread_id": f'{state["session_id"]}:{state["run_id"]}:{branch_id}'
                        },
                        "recursion_limit": MAX_AGENT_TURNS,
                    },
                ):
                    if event.get("type") == "token":
                        output += event.get("delta", "")
                        _emit(
                            conn,
                            branch_state,
                            "agent.delta",
                            legacy_event=event,
                            data={"agent_id": target_agent, "delta": event.get("delta", "")},
                            node_name="parallel_dispatch",
                            agent_id=target_agent,
                        )
                    elif event.get("type") in {"tool_start", "tool_end"}:
                        normalized = (
                            "tool.started" if event["type"] == "tool_start" else "tool.completed"
                        )
                        _emit(
                            conn,
                            branch_state,
                            normalized,
                            legacy_event=event,
                            data={key: value for key, value in event.items() if key != "type"},
                            node_name="parallel_dispatch",
                            agent_id=target_agent,
                        )
                _save_message(
                    conn,
                    message_id=str(uuid.uuid4()),
                    session_id=state["session_id"],
                    agent_id=target_agent,
                    role="assistant",
                    content=output,
                )
                mark_execution(
                    conn,
                    idempotency_key,
                    "succeeded",
                    result={"branch_id": branch_id, "output_chars": len(output)},
                )
                conn.execute(
                    "UPDATE handoff_proposals SET status='executed' WHERE id=?",
                    (proposal["id"],),
                )
                conn.commit()
                _emit(
                    conn,
                    branch_state,
                    "branch.completed",
                    data={"output_chars": len(output)},
                    node_name="parallel_dispatch",
                    agent_id=target_agent,
                )
                return {
                    "branch_id": branch_id,
                    "agent_id": target_agent,
                    "status": "completed",
                    "output": output,
                    "error": "",
                }
            except Exception as exc:
                mark_execution(conn, idempotency_key, "failed", error_msg=str(exc))
                _emit(
                    conn,
                    branch_state,
                    "branch.failed",
                    legacy_event={
                        "type": "warning",
                        "agentId": target_agent,
                        "message": f"并行分支失败：{exc}",
                    },
                    data={"message": str(exc)},
                    node_name="parallel_dispatch",
                    agent_id=target_agent,
                )
                return {
                    "branch_id": branch_id,
                    "agent_id": target_agent,
                    "status": "failed",
                    "output": output,
                    "error": str(exc),
                }

        results = await asyncio.gather(
            *(run_branch(proposal) for proposal in state["approved_proposals"])
        )
        _emit(
            conn,
            state,
            "node.completed",
            data={
                "branches": len(results),
                "completed": sum(result["status"] == "completed" for result in results),
                "failed": sum(result["status"] == "failed" for result in results),
            },
            node_name="join",
        )
        return {"branch_results": results, "verdict": "branches_joined"}

    async def compose_final(state: GraphRuntimeState) -> dict:
        completed_outputs = [
            result["output"]
            for result in state["branch_results"]
            if result["status"] == "completed" and result["output"]
        ]
        final_output = "\n\n".join(completed_outputs) or state["current_output"]
        return {"final_output": final_output}

    async def persist_result(state: GraphRuntimeState) -> dict:
        status = "failed" if state.get("error") else "completed"
        conn.execute(
            """UPDATE agent_runs
               SET status=?, current_node='persist_result', final_verdict=?,
                   final_output=?, error_json=?,
                   completed_at=datetime('now')
               WHERE id=?""",
            (
                status,
                state["verdict"],
                state["final_output"],
                "{}" if not state.get("error") else str(state["error"]),
                state["run_id"],
            ),
        )
        conn.commit()
        _emit(
            conn,
            state,
            "run.failed" if status == "failed" else "run.completed",
            legacy_event={
                "type": "done",
                "session_id": state["session_id"],
                "trace_id": state["run_id"],
            },
            data={"status": status, "verdict": state["verdict"]},
            node_name="persist_result",
        )
        return {}

    builder = StateGraph(GraphRuntimeState)
    builder.add_node("accept_input", accept_input)
    builder.add_node("assemble_context", assemble_context_node)
    builder.add_node("select_agent", select_agent)
    builder.add_node("execute_agent", execute_agent)
    builder.add_node("parse_proposals", parse_proposals)
    builder.add_node("govern", govern)
    builder.add_node("approval_wait", approval_wait)
    builder.add_node("serial_dispatch", serial_dispatch)
    builder.add_node("parallel_dispatch", parallel_dispatch)
    builder.add_node("compose_final", compose_final)
    builder.add_node("persist_result", persist_result)
    builder.set_entry_point("accept_input")
    builder.add_edge("accept_input", "assemble_context")
    builder.add_edge("assemble_context", "select_agent")
    builder.add_edge("select_agent", "execute_agent")
    builder.add_edge("execute_agent", "parse_proposals")
    builder.add_edge("parse_proposals", "govern")
    builder.add_conditional_edges("govern", route_after_govern)
    builder.add_conditional_edges("approval_wait", route_after_approval)
    builder.add_edge("serial_dispatch", "execute_agent")
    builder.add_edge("parallel_dispatch", "compose_final")
    builder.add_edge("compose_final", "persist_result")
    builder.add_edge("persist_result", END)
    return builder.compile(checkpointer=checkpointer)


async def route_graph_stream(
    user_input: str,
    session_id: str,
    conn: sqlite3.Connection,
    prompt_version: str = "v4",
    trace_id: str = "",
    checkpoint_path: str | Path | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    run_id = create_run(
        conn,
        session_id=session_id,
        prompt_version=prompt_version,
        run_id=trace_id or None,
    )
    initial_state: GraphRuntimeState = {
        "run_id": run_id,
        "session_id": session_id,
        "user_message_id": str(uuid.uuid4()),
        "prompt_version": prompt_version,
        "user_input": user_input,
        "cleaned_input": user_input,
        "current_agent": "knowledge",
        "current_branch_id": "root",
        "depth": 0,
        "turn_count": 0,
        "active_messages": [],
        "current_output": "",
        "current_tool_events": [],
        "agent_results": [],
        "proposals": [],
        "decisions": [],
        "approved_proposals": [],
        "branch_results": [],
        "pending_approval": None,
        "verdict": "incomplete",
        "final_output": "",
        "error": None,
    }
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    checkpoint_file = str(checkpoint_path or CHECKPOINT_DB)
    Path(checkpoint_file).parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(checkpoint_file) as checkpointer:
        graph = build_router_graph(conn, checkpointer)
        config = {
            "configurable": {
                "thread_id": run_id,
            },
            "recursion_limit": 30,
        }
        async for event in _run_graph_command(
            graph, initial_state, config, conn, run_id, queue
        ):
            yield event


async def resume_graph_stream(
    run_id: str,
    resolution: dict[str, Any],
    conn: sqlite3.Connection,
    checkpoint_path: str | Path | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    run = conn.execute(
        "SELECT session_id, status FROM agent_runs WHERE id=?", (run_id,)
    ).fetchone()
    if run is None:
        raise LookupError("run not found")
    if run["status"] != "waiting_approval":
        raise ValueError("run is not waiting for approval")
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    checkpoint_file = str(checkpoint_path or CHECKPOINT_DB)
    async with AsyncSqliteSaver.from_conn_string(checkpoint_file) as checkpointer:
        graph = build_router_graph(conn, checkpointer)
        config = {
            "configurable": {
                "thread_id": run_id,
            },
            "recursion_limit": 30,
        }
        snapshot = await graph.aget_state(config)
        state = snapshot.values
        approval = state.get("pending_approval")
        if not approval:
            raise ValueError("checkpoint has no pending approval")
        approved = bool(resolution.get("approved"))
        status = "approved" if approved else "rejected"
        conn.execute(
            """UPDATE approval_requests
               SET status=?, decision_json=?, resolved_at=datetime('now','localtime')
               WHERE id=? AND status='pending'""",
            (status, json.dumps(resolution, ensure_ascii=False), approval["approval_id"]),
        )
        conn.execute(
            """UPDATE handoff_proposals SET status=?, updated_at=datetime('now','localtime')
               WHERE id=?""",
            ("allow" if approved else "deny", approval["proposal_id"]),
        )
        conn.execute(
            "UPDATE agent_runs SET status='running', current_node='approval_wait' WHERE id=?",
            (run_id,),
        )
        conn.commit()
        proposal = next(
            (
                item
                for item in state["proposals"]
                if item["id"] == approval["proposal_id"]
            ),
            None,
        )
        envelope = append_run_event(
            conn,
            run_id=run_id,
            branch_id=state.get("current_branch_id", ""),
            event_type="approval.resolved",
            data={"approval_id": approval["approval_id"], "approved": approved},
            node_name="approval_wait",
            agent_id="router",
        )
        queue.put_nowait(
            {
                "envelope": envelope,
                "legacy": {
                    "type": "approval_resolved",
                    "agentId": "router",
                    "approval_id": approval["approval_id"],
                    "approved": approved,
                },
            }
        )
        target = "serial_dispatch" if approved and proposal else "compose_final"
        update = {
            "approved_proposals": [proposal] if approved and proposal else [],
            "pending_approval": None,
            "verdict": "approval_granted" if approved else "approval_rejected",
        }
        async for event in _run_graph_command(
            graph,
            Command(update=update, goto=target),
            config,
            conn,
            run_id,
            queue,
        ):
            yield event


async def _run_graph_command(
    graph,
    command,
    config: dict[str, Any],
    conn: sqlite3.Connection,
    run_id: str,
    queue: asyncio.Queue[dict[str, Any] | None],
) -> AsyncGenerator[dict[str, Any], None]:
    async def run_graph() -> None:
        token = _active_sink.set(queue.put_nowait)
        try:
            await graph.ainvoke(command, config=config)
        except Exception as exc:
            conn.execute(
                """UPDATE agent_runs SET status='failed', final_verdict='runtime_error',
                   error_json=?, completed_at=datetime('now') WHERE id=?""",
                (str(exc), run_id),
            )
            conn.commit()
            queue.put_nowait(
                {
                    "envelope": None,
                    "legacy": {"type": "error", "agentId": "router", "message": str(exc)},
                }
            )
        finally:
            _active_sink.reset(token)
            queue.put_nowait(None)

    task = asyncio.create_task(run_graph())
    while True:
        item = await queue.get()
        if item is None:
            break
        legacy_event = item.get("legacy")
        if legacy_event:
            yield legacy_event
    await task
