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

export const AGENT_META: Record<string, { label: string; role: string; color: string }> = {
  knowledge: { label: "Knowledge", role: "整理与检索", color: "#7c9cff" },
  review: { label: "Review", role: "质疑与校验", color: "#ffb86b" },
  brain: { label: "Brain", role: "联想与扩展", color: "#b88cff" },
  router: { label: "Router", role: "链路调度", color: "#6dd6c0" },
  user: { label: "User", role: "原始输入", color: "#aab4c3" },
};

export function agentMeta(agentId: string) {
  return AGENT_META[agentId] || {
    label: agentId || "System",
    role: "执行节点",
    color: "#aab4c3",
  };
}

export function formatLatency(ms: number): string {
  if (!ms) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

export function formatCost(usd: number): string {
  if (!usd) return "$0";
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
    verified: "链路可信",
    degraded: "链路有告警",
    partial: "证据不完整",
    compromised: "链路校验失败",
  }[status];
}

export function verdictLabel(verdict: string): string {
  const labels: Record<string, string> = {
    natural_end: "自然完成",
    missing_handoff: "疑似缺少接力",
    loop_detected: "检测到循环",
    max_depth_reached: "达到链路上限",
    incomplete: "执行未完成",
    legacy: "历史记录",
  };
  return labels[verdict] || verdict || "未知结果";
}

export function verdictDescription(verdict: string): string {
  const descriptions: Record<string, string> = {
    natural_end: "Agent 已给出完整答复，链路正常结束。",
    missing_handoff: "输出可能暗示需要其他 Agent，但没有明确写出 @agent 接力指令。",
    loop_detected: "相同 Agent 接力路径重复出现，系统已主动终止。",
    max_depth_reached: "执行达到安全深度上限，系统已停止继续接力。",
    incomplete: "缺少结束事件，执行可能被中断或仍在进行。",
    legacy: "仅保留了模型调用记录，无法还原完整执行链路。",
  };
  return descriptions[verdict] || "查看时间线了解本次执行如何结束。";
}

export function eventLabel(type: string): string {
  const labels: Record<string, string> = {
    trace_start: "请求开始",
    input_received: "接收输入",
    context_assembled: "组装上下文",
    agent_start: "Agent 开始",
    llm_call: "模型调用",
    tool_start: "调用工具",
    tool_end: "工具返回",
    retrieval_completed: "检索完成",
    citation_verified: "引用已验证",
    handoff: "Agent 接力",
    warning: "链路告警",
    verdict: "终止判定",
    agent_end: "Agent 完成",
    error: "执行错误",
    trace_end: "请求结束",
  };
  return labels[type] || type;
}

export function eventTone(event: TraceEvent): "neutral" | "info" | "success" | "warning" | "danger" {
  if (event.status === "error" || event.event_type === "error") return "danger";
  if (event.status === "warning" || event.event_type === "warning") return "warning";
  if (["trace_end", "agent_end", "citation_verified"].includes(event.event_type)) return "success";
  if (["llm_call", "tool_start", "tool_end", "retrieval_completed", "handoff", "verdict"].includes(event.event_type)) return "info";
  return "neutral";
}

export function eventSummary(event: TraceEvent): string {
  const payload = event.payload || {};
  switch (event.event_type) {
    case "trace_start":
      return "已创建本次执行链路，并开始记录事件。";
    case "input_received":
      return `收到 ${payload.char_count || 0} 个字符的用户输入`;
    case "context_assembled":
      return `从 ${payload.history_message_count || 0} 条历史消息组装为 ${payload.final_message_count || 0} 条有效上下文`;
    case "agent_start":
      return `${agentMeta(event.agent_id).label} 开始处理${payload.depth !== undefined ? `，链路深度 ${payload.depth}` : ""}`;
    case "llm_call":
      return `${event.name || "模型"} · ${(payload.input_tokens || 0).toLocaleString()} 输入 / ${(payload.output_tokens || 0).toLocaleString()} 输出 Token · ${formatLatency(payload.latency_ms || 0)}`;
    case "tool_start":
      return `${agentMeta(event.agent_id).label} 请求调用 ${event.name || "工具"}`;
    case "tool_end":
      return `${event.name || "工具"} 已${event.status === "error" ? "失败" : "返回结果"}`;
    case "retrieval_completed":
      return `从 ${payload.candidate_count || 0} 个候选中选中 ${payload.selected?.length || 0} 条相关笔记`;
    case "handoff":
      return `${agentMeta(payload.from_agent || event.parent_agent_id).label} → ${agentMeta(payload.to_agent || event.agent_id).label}${event.name ? ` · ${event.name}` : ""}`;
    case "citation_verified":
      return `笔记 ${payload.note_id || event.name} 已通过 ${payload.method || "精确 ID"} 校验`;
    case "verdict":
      return `${verdictLabel(event.name)} · ${payload.should_terminate ? "结束链路" : "继续执行"}`;
    case "agent_end":
      return `${agentMeta(event.agent_id).label} 输出 ${payload.output_chars || 0} 字符，使用 ${payload.tool_call_count || 0} 次工具`;
    case "trace_end":
      return verdictDescription(payload.verdict || event.name);
    case "error":
    case "warning":
      return payload.message || event.name;
    default:
      return event.name || event.status || "事件已记录";
  }
}

export function importantEvents(events: TraceEvent[]): TraceEvent[] {
  const important = new Set([
    "agent_start",
    "llm_call",
    "tool_start",
    "tool_end",
    "retrieval_completed",
    "handoff",
    "warning",
    "error",
    "verdict",
    "agent_end",
    "trace_end",
  ]);
  return events.filter((event) => important.has(event.event_type));
}
