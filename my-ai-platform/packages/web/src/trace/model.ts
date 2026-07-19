export type TrustStatus = "verified" | "degraded" | "partial" | "compromised";

export interface TraceSummary {
  trace_id: string;
  session_id: string;
  agents: string[];
  status: TrustStatus;
  trust_score: number;
  event_count: number;
  call_count: number;
  tool_count: number;
  retrieval_count: number;
  latency_ms: number;
  cost_usd: number;
  verdict: string;
  started_at: string;
  ended_at: string;
  legacy: boolean;
}

export interface TraceEvent {
  id: string;
  sequence: number;
  event_type: string;
  phase_trace_id: string;
  session_id?: string;
  agent_id: string;
  parent_agent_id: string;
  status: string;
  name: string;
  payload: Record<string, any>;
  prev_hash?: string;
  event_hash?: string;
  created_at: string;
}

export interface TraceTrust {
  status: TrustStatus;
  score: number;
  ledger: {
    valid: boolean;
    event_count: number;
    head_hash: string;
    issues: string[];
  };
  missing_required_events: string[];
  structural_issues: string[];
  open_tool_calls: Array<{ tool_call_id: string; name: string; agent_id: string }>;
  error_count: number;
  warning_count: number;
  retrieved_note_count: number;
  verified_citation_count: number;
  citation_coverage: number | null;
  claim: string;
}

export interface TraceDetail {
  trace_id: string;
  requested_trace_id: string;
  scope: "root" | "phase" | "legacy_phase";
  session_id: string;
  user_input: {
    content: string;
    sha256?: string;
    truncated?: boolean;
    created_at: string;
  } | null;
  events: TraceEvent[];
  agents: Array<{
    agent_id: string;
    phase_trace_ids: string[];
    call_count: number;
    timeline: TraceEvent[];
  }>;
  errors: TraceEvent[];
  evidence: {
    retrievals: TraceEvent[];
    citations: Array<{
      note_id: string;
      agent_id: string;
      verification: string;
      sequence: number;
    }>;
  };
  trust: TraceTrust;
  summary: {
    total_tokens: number;
    total_cost_usd: number;
    total_latency_ms: number;
    call_count: number;
    tool_count: number;
    retrieval_count: number;
    handoff_count: number;
    agent_count: number;
    verdict: string;
    status: string;
    started_at: string;
    ended_at: string;
  };
}

export function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

export function formatCost(usd: number): string {
  if (usd < 0.001) return "< $0.001";
  return `$${usd.toFixed(4)}`;
}

export function formatTraceTime(timestamp: string): string {
  if (!timestamp) return "";
  const normalized = timestamp.includes("T") ? timestamp : timestamp.replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return timestamp;
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function trustLabel(status: TrustStatus): string {
  return {
    verified: "链路已校验",
    degraded: "链路有错误",
    partial: "证据不完整",
    compromised: "校验失败",
  }[status];
}

export function eventLabel(type: string): string {
  const labels: Record<string, string> = {
    trace_start: "请求开始",
    input_received: "收到输入",
    context_assembled: "上下文组装",
    agent_start: "Agent 开始",
    llm_call: "模型调用",
    tool_start: "工具开始",
    tool_end: "工具结束",
    retrieval_completed: "检索完成",
    citation_verified: "引用已验证",
    handoff: "Agent 交接",
    warning: "链路警告",
    verdict: "终止判定",
    agent_end: "Agent 结束",
    error: "执行错误",
    trace_end: "请求结束",
  };
  return labels[type] || type;
}

export function eventSummary(event: TraceEvent): string {
  const payload = event.payload || {};
  switch (event.event_type) {
    case "input_received":
      return `${payload.char_count || 0} 字符 · SHA ${String(payload.content_sha256 || "").slice(0, 10)}`;
    case "context_assembled":
      return `${payload.history_message_count || 0} 条历史 → ${payload.final_message_count || 0} 条上下文`;
    case "agent_start":
      return `${event.agent_id} · depth ${payload.depth ?? "parallel"}`;
    case "llm_call":
      return `${event.name} · ${payload.input_tokens || 0}+${payload.output_tokens || 0} tokens · ${formatLatency(payload.latency_ms || 0)}`;
    case "tool_start":
      return event.name;
    case "tool_end":
      return `${event.name} · ${event.status}`;
    case "retrieval_completed":
      return `${payload.candidate_count || 0} 个候选 · 选中 ${payload.selected?.length || 0}`;
    case "handoff":
      return `${payload.from_agent || event.parent_agent_id} → ${payload.to_agent || event.agent_id} · ${event.name}`;
    case "citation_verified":
      return `${payload.note_id || event.name} · ${payload.method || "exact"}`;
    case "verdict":
      return `${event.name} · ${payload.should_terminate ? "结束" : "继续"}`;
    case "agent_end":
      return `${event.agent_id} · ${payload.output_chars || 0} 字符 · ${payload.tool_call_count || 0} 次工具`;
    case "trace_end":
      return payload.verdict || event.name;
    case "error":
    case "warning":
      return payload.message || event.name;
    default:
      return event.name || event.status;
  }
}
