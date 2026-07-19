import type { InsightChipData } from "../components/InsightChip.vue";

export const TAG_AGENT_MAP: Record<string, string> = {
  review: "review",
  critique: "review",
  brain: "brain",
};

export const TAG_LABEL: Record<string, string> = {
  review: "Review Agent",
  critique: "Review Agent",
  brain: "Brain Agent",
};

export const AGENT_VERB: Record<string, string> = {
  knowledge: "正在整理相关记忆",
  review: "正在挑战你的假设",
  brain: "正在做联想扩展",
};

export const AGENT_ICON: Record<string, string> = {
  review: "R",
  brain: "B",
  knowledge: "K",
};

export const AGENT_TRACE_BG: Record<string, string> = {
  review: "rgba(255,184,107,0.1)",
  brain: "rgba(184,140,255,0.1)",
  knowledge: "rgba(124,156,255,0.1)",
};

export const AGENT_TRACE_COLOR: Record<string, string> = {
  review: "#FFB86B",
  brain: "#B88CFF",
  knowledge: "#7C9CFF",
};

export const COMMANDS = [
  { trigger: "/review", label: "Review Agent", desc: "审视你的想法", color: "#FFB86B", bg: "rgba(255,184,107,0.06)", border: "rgba(255,184,107,0.2)" },
  { trigger: "/brain", label: "Brain Agent", desc: "联想扩展", color: "#B88CFF", bg: "rgba(184,140,255,0.06)", border: "rgba(184,140,255,0.2)" },
];

export interface ToolCall {
  name: string;
  input?: Record<string, unknown>;
  result?: string;
  status: "running" | "done";
  expanded?: boolean;
  isError?: boolean;
}

export interface HandoffStep {
  from: string;
  to: string;
  trigger: string;
  traceId?: string;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  agentId?: string;
  done?: boolean;
  toolCalls?: ToolCall[];
  insightChips?: InsightChipData[];
  isSwitchBanner?: boolean;
  timestamp: number;
}

export function parseTag(text: string): { tag: string; label: string } | null {
  const match = text.match(/#([a-zA-Z][a-zA-Z0-9_-]*)/);
  if (!match) return null;
  const tag = match[1].toLowerCase();
  return tag in TAG_AGENT_MAP ? { tag, label: TAG_LABEL[tag] } : null;
}

export function getOrCreateSessionId(): string {
  const key = "chat_session_id";
  let sessionId = sessionStorage.getItem(key);
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    sessionStorage.setItem(key, sessionId);
  }
  return sessionId;
}

export function buildChipsFromTool(name: string, result: string, agentId: string): InsightChipData[] {
  const suffix = `-${agentId}-${Date.now()}`;
  if (name === "search_notes") {
    try {
      const parsed = JSON.parse(result);
      const count = Array.isArray(parsed) ? parsed.length : parsed.results?.length || parsed.notes?.length || 0;
      return [{ id: `ref${suffix}`, type: "note_ref", label: `引用 ${count} 条笔记`, count }];
    } catch {
      return [{ id: `ref${suffix}`, type: "note_ref", label: "检索笔记" }];
    }
  }
  if (name === "save_note") return [{ id: `saved${suffix}`, type: "saved", label: "已保存为笔记" }];
  if (name === "archive_note") return [{ id: `arch${suffix}`, type: "tool_result", label: "已归档" }];
  if (name === "synthesize_notes") return [{ id: `syn${suffix}`, type: "note_ref", label: "合成笔记" }];
  return [{ id: `${name}${suffix}`, type: "tool_result", label: name }];
}

export function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

export function formatCost(usd: number): string {
  return `$${usd.toFixed(4)}`;
}

