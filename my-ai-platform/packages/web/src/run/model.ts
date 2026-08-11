export type RunStatus =
  | "created"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancelled";

export interface RunEvent<T = Record<string, unknown>> {
  event_id: string;
  run_id: string;
  branch_id: string;
  sequence: number;
  type: string;
  timestamp: string;
  node_name: string;
  agent_id: string;
  data: T;
}

export interface AgentProjection {
  agentId: string;
  branchId: string;
  status: "idle" | "running" | "completed" | "failed";
  output: string;
  activeTool: string;
}

export interface ApprovalProjection {
  approvalId: string;
  proposalId: string;
  targetAgent: string;
  risk: string;
  reason: string;
  status: "pending" | "approved" | "rejected";
}

export interface RunProjection {
  runId: string;
  status: RunStatus;
  currentNode: string;
  agents: Record<string, AgentProjection>;
  approvals: ApprovalProjection[];
  timeline: RunEvent[];
  finalOutput: string;
  lastSequence: number;
}

export function createRunProjection(runId: string): RunProjection {
  return {
    runId,
    status: "created",
    currentNode: "",
    agents: {},
    approvals: [],
    timeline: [],
    finalOutput: "",
    lastSequence: 0,
  };
}

export function reduceRunEvent(state: RunProjection, event: RunEvent): RunProjection {
  if (event.run_id !== state.runId || event.sequence <= state.lastSequence) return state;
  const next: RunProjection = {
    ...state,
    agents: { ...state.agents },
    approvals: [...state.approvals],
    timeline: [...state.timeline, event],
    lastSequence: event.sequence,
  };
  const data = event.data as Record<string, unknown>;
  const agentId = event.agent_id || String(data.agent_id || "");
  next.currentNode = event.node_name || next.currentNode;
  const agentKey = `${event.branch_id || "root"}:${agentId}`;

  if (event.type === "run.started") next.status = "running";
  if (event.type === "run.completed") next.status = "completed";
  if (event.type === "run.failed") next.status = "failed";
  if (event.type === "run.cancelled") next.status = "cancelled";

  if (event.type === "agent.started" && agentId) {
    next.agents[agentKey] = {
      agentId,
      branchId: event.branch_id,
      status: "running",
      output: next.agents[agentKey]?.output || "",
      activeTool: "",
    };
  }
  if (event.type === "agent.delta" && agentId) {
    const current = next.agents[agentKey] || {
      agentId,
      branchId: event.branch_id,
      status: "running" as const,
      output: "",
      activeTool: "",
    };
    next.agents[agentKey] = { ...current, output: current.output + String(data.delta || "") };
  }
  if ((event.type === "agent.completed" || event.type === "branch.completed") && agentId) {
    const current = next.agents[agentKey];
    if (current) next.agents[agentKey] = { ...current, status: "completed", activeTool: "" };
  }
  if ((event.type === "agent.failed" || event.type === "branch.failed") && agentId) {
    const current = next.agents[agentKey];
    if (current) next.agents[agentKey] = { ...current, status: "failed", activeTool: "" };
  }
  if (event.type === "tool.started" && agentId) {
    const current = next.agents[agentKey];
    if (current) next.agents[agentKey] = { ...current, activeTool: String(data.name || "") };
  }
  if ((event.type === "tool.completed" || event.type === "tool.failed") && agentId) {
    const current = next.agents[agentKey];
    if (current) next.agents[agentKey] = { ...current, activeTool: "" };
  }
  if (event.type === "approval.required") {
    next.status = "waiting_approval";
    next.approvals.push({
      approvalId: String(data.approval_id || ""),
      proposalId: String(data.proposal_id || ""),
      targetAgent: String(data.target_agent || ""),
      risk: String(data.risk || ""),
      reason: String(data.reason || ""),
      status: "pending",
    });
  }
  if (event.type === "approval.resolved") {
    next.status = "running";
    const approvalId = String(data.approval_id || "");
    next.approvals = next.approvals.map((approval) =>
      approval.approvalId === approvalId
        ? { ...approval, status: data.approved ? "approved" : "rejected" }
        : approval,
    );
  }
  return next;
}
