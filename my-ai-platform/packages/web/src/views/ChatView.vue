<script setup lang="ts">
import { ref, nextTick, onUnmounted, computed } from "vue";
import AgentDivider from "../components/AgentDivider.vue";
import AgentTraceBar from "../components/AgentTraceBar.vue";
import ThoughtBlock from "../components/ThoughtBlock.vue";
import type { InsightChipData } from "../components/InsightChip.vue";
import ThoughtComposer from "../components/ThoughtComposer.vue";

// ── Agent 配置 ──
const TAG_AGENT_MAP: Record<string, string> = {
  review: "review",
  critique: "review",
  brain: "brain",
};

const TAG_LABEL: Record<string, string> = {
  review: "Review Agent",
  critique: "Review Agent",
  brain: "Brain Agent",
};

const AGENT_VERB: Record<string, string> = {
  review: "正在挑战你的假设",
  brain: "正在做联想扩展",
};

const AGENT_ICON: Record<string, string> = {
  review: "R",
  brain: "B",
  knowledge: "K",
};

const AGENT_TRACE_BG: Record<string, string> = {
  review: "rgba(255,184,107,0.1)",
  brain: "rgba(184,140,255,0.1)",
  knowledge: "rgba(124,156,255,0.1)",
};
const AGENT_TRACE_COLOR: Record<string, string> = {
  review: "#FFB86B",
  brain: "#B88CFF",
  knowledge: "#7C9CFF",
};

function parseTag(text: string): { tag: string; label: string } | null {
  const m = text.match(/#([a-zA-Z][a-zA-Z0-9_-]*)/);
  if (!m) return null;
  const tag = m[1].toLowerCase();
  if (tag in TAG_AGENT_MAP) return { tag, label: TAG_LABEL[tag] };
  return null;
}

// ── 数据结构 ──
interface ToolCall {
  name: string;
  input?: Record<string, unknown>;
  result?: string;
  status: "running" | "done";
  expanded?: boolean;
  isError?: boolean;
}

interface HandoffStep {
  from: string;
  to: string;
  trigger: string;
  traceId?: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  agentId?: string;
  done?: boolean;
  toolCalls?: ToolCall[];
  insightChips?: InsightChipData[];
  isSwitchBanner?: boolean;
  timestamp: number;
}

const SESSION_KEY = "chat_session_id";
function getOrCreateSessionId(): string {
  let sid = sessionStorage.getItem(SESSION_KEY);
  if (!sid) {
    sid = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, sid);
  }
  return sid;
}
const sessionId = getOrCreateSessionId();

const emit = defineEmits<{ noteSaved: [] }>();

const messages = ref<Message[]>([]);
const input = ref("");
const streaming = ref(false);
const activeTag = computed(() => parseTag(input.value));
const messagesEl = ref<HTMLElement | null>(null);

// ── 命令 ──
const COMMANDS = [
  { trigger: "/review", label: "Review Agent", desc: "审视你的想法", color: "#FFB86B", bg: "rgba(255,184,107,0.06)", border: "rgba(255,184,107,0.2)" },
  { trigger: "/brain", label: "Brain Agent", desc: "联想扩展", color: "#B88CFF", bg: "rgba(184,140,255,0.06)", border: "rgba(184,140,255,0.2)" },
];

let abortController: AbortController | null = null;

// ── 智能滚动 ──
const userScrolledUp = ref(false);
const SCROLL_BOTTOM_THRESHOLD = 48;

function isNearBottom(): boolean {
  const el = messagesEl.value;
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_BOTTOM_THRESHOLD;
}

function onMessagesScroll() {
  userScrolledUp.value = !isNearBottom();
}

// ── Stale watchdog ──
const STALE_TIMEOUT_MS = 30_000;
let staleTimer: ReturnType<typeof setTimeout> | null = null;
const showStaleWarning = ref(false);

function resetStaleTimer() {
  if (staleTimer) clearTimeout(staleTimer);
  showStaleWarning.value = false;
  staleTimer = setTimeout(() => {
    showStaleWarning.value = true;
  }, STALE_TIMEOUT_MS);
}

function clearStaleTimer() {
  if (staleTimer) { clearTimeout(staleTimer); staleTimer = null; }
  showStaleWarning.value = false;
}

// ── Trace 面板 ──
const traceId = ref<string | null>(null);
const defaultTraceId = ref<string | null>(null);  // 默认显示的 trace（首个 phase），per-phase 切换后可恢复
const traceExpanded = ref(false);
interface TraceCall {
  id: string; agent_id: string; model: string;
  input_tokens: number; output_tokens: number;
  cost_usd: number; latency_ms: number; status: string; created_at: string;
}
interface TraceAgent {
  agent_id: string;
  calls: TraceCall[];
  subtotal: { tokens: number; cost_usd: number; latency_ms: number; call_count: number };
}
interface TraceData {
  trace_id: string;
  agents: TraceAgent[];
  summary: { total_tokens: number; total_cost_usd: number; total_latency_ms: number; call_count: number };
}
const traceData = ref<TraceData | null>(null);
const traceLoading = ref(false);
const phaseTraceLabel = ref<string | null>(null);  // 当前查看的是哪个 phase 的 trace

async function fetchTrace(tid?: string) {
  const targetId = tid || traceId.value;
  if (!targetId || traceLoading.value) return;
  traceLoading.value = true;
  try {
    const res = await fetch(`/trace/${targetId}`);
    if (res.ok) traceData.value = await res.json();
  } catch { /* ignore */ }
  finally { traceLoading.value = false; }
}

function toggleTrace() {
  traceExpanded.value = !traceExpanded.value;
  if (traceExpanded.value && !traceData.value) fetchTrace();
}

function onPhaseTraceClick(pid: string) {
  // 保存当前默认 traceId（如果还没保存）
  if (!defaultTraceId.value) defaultTraceId.value = traceId.value;
  phaseTraceLabel.value = pid.slice(0, 8);
  traceExpanded.value = true;
  traceData.value = null;
  traceId.value = pid;
  fetchTrace(pid);
}

// 重置 per-phase trace 视图，回到默认 trace
function resetToGlobalTrace() {
  phaseTraceLabel.value = null;
  traceId.value = defaultTraceId.value;
  traceData.value = null;
  traceExpanded.value = false;
}

function formatMs(ms: number): string {
  if (ms >= 1000) return (ms / 1000).toFixed(1) + "s";
  return ms + "ms";
}
function formatCost(usd: number): string {
  return "$" + usd.toFixed(4);
}
function formatTime(ts: number): string {
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

// ── 并行 Agent 状态 ──
const agentToolStatus = ref<Record<string, string | null>>({});

// ── Insight Chips 累积 ──
const accumulatedChips = ref<Record<string, InsightChipData[]>>({});

function buildChipsFromTool(name: string, result: string, agentId: string): InsightChipData[] {
  const chips: InsightChipData[] = [];
  const suffix = `-${agentId}-${Date.now()}`;
  if (name === "search_notes") {
    try {
      const r = JSON.parse(result);
      const count = Array.isArray(r) ? r.length : r.results?.length || r.notes?.length || 0;
      chips.push({ id: `ref${suffix}`, type: "note_ref", label: `引用 ${count} 条笔记`, count });
    } catch { chips.push({ id: `ref${suffix}`, type: "note_ref", label: "检索笔记" }); }
  } else if (name === "save_note") {
    chips.push({ id: `saved${suffix}`, type: "saved", label: "已保存为笔记" });
  } else if (name === "archive_note") {
    chips.push({ id: `arch${suffix}`, type: "tool_result", label: "已归档" });
  } else if (name === "synthesize_notes") {
    chips.push({ id: `syn${suffix}`, type: "note_ref", label: "合成笔记" });
  } else {
    chips.push({ id: `${name}${suffix}`, type: "tool_result", label: name });
  }
  return chips;
}

const runningAgents = computed(() => {
  return Object.entries(agentToolStatus.value)
    .filter(([, tool]) => tool !== null)
    .map(([agentId, toolName]) => {
      const label = TAG_LABEL[agentId] || agentId;
      return `${label} 正在调用 ${toolName}...`;
    });
});

// ── Handoff Chain 追踪 ──
const handoffSteps = ref<HandoffStep[]>([]);
const currentVerdict = ref<string | null>(null);
const currentVerdictReason = ref<string | null>(null);

async function scrollBottom(force = false) {
  await nextTick();
  if (messagesEl.value && (force || !userScrolledUp.value)) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
    userScrolledUp.value = false;
  }
}

function resetToolStatus() {
  agentToolStatus.value = {};
}

// ── 手动 SSE 流解析器 ──
async function readSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: (eventType: string, data: string) => void,
  signal: AbortSignal,
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      if (signal.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");

      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";

      for (const part of parts) {
        if (!part.trim()) continue;
        const lines = part.split("\n");
        let eventType = "";
        let data = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            data = line.slice(6);
          }
        }
        if (eventType) onEvent(eventType, data);
      }
    }

    if (buffer.trim()) {
      const lines = buffer.split("\n");
      let eventType = "";
      let data = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          data = line.slice(6);
        }
      }
      if (eventType) onEvent(eventType, data);
    }
  } catch (err: unknown) {
    if (!signal.aborted) console.error("SSE stream read error:", err);
  } finally {
    reader.releaseLock();
  }
}

// ── 发送 ──
function sendMessage() {
  if (!input.value.trim() || streaming.value) return;

  const userInput = input.value;
  messages.value.push({ role: "user", content: userInput, done: true, timestamp: Date.now() });
  streaming.value = true;
  traceId.value = null;
  defaultTraceId.value = null;
  phaseTraceLabel.value = null;
  traceData.value = null;
  traceExpanded.value = false;
  handoffSteps.value = [];
  accumulatedChips.value = {};
  currentVerdict.value = null;
  currentVerdictReason.value = null;
  input.value = "";
  scrollBottom(true);

  abortController = new AbortController();
  let lastAgentId = "knowledge";

  function handleEvent(eventType: string, data: string) {
    resetStaleTimer();
    switch (eventType) {
      case "token": {
        const parsed = JSON.parse(data);
        let target: Message | null = null;
        for (let i = messages.value.length - 1; i >= 0; i--) {
          const m = messages.value[i];
          if (m.role === "assistant" && !m.done && m.agentId === parsed.agentId && !m.isSwitchBanner) {
            target = m;
            break;
          }
        }
        if (target) {
          target.content += parsed.delta;
        } else {
          messages.value.push({ role: "assistant", content: parsed.delta, agentId: parsed.agentId, done: false, timestamp: Date.now() });
        }
        scrollBottom();
        break;
      }

      case "tool_start": {
        const parsed = JSON.parse(data);
        agentToolStatus.value[parsed.agentId] = parsed.name;
        let target: Message | null = null;
        for (let i = messages.value.length - 1; i >= 0; i--) {
          const m = messages.value[i];
          if (m.role === "assistant" && !m.done && m.agentId === parsed.agentId && !m.isSwitchBanner) {
            target = m;
            break;
          }
        }
        if (target) {
          if (!target.toolCalls) target.toolCalls = [];
          target.toolCalls.push({ name: parsed.name, input: parsed.input, status: "running" });
        }
        break;
      }

      case "tool_end": {
        const parsed = JSON.parse(data);
        agentToolStatus.value[parsed.agentId] = null;
        let target: Message | null = null;
        for (let i = messages.value.length - 1; i >= 0; i--) {
          const m = messages.value[i];
          if (m.role === "assistant" && !m.done && m.agentId === parsed.agentId && !m.isSwitchBanner) {
            target = m;
            break;
          }
        }
        if (target?.toolCalls) {
          for (let tc = target.toolCalls.length - 1; tc >= 0; tc--) {
            if (target.toolCalls[tc].name === parsed.name && target.toolCalls[tc].status === "running") {
              target.toolCalls[tc].result = parsed.result;
              target.toolCalls[tc].status = "done";
              try {
                const r = JSON.parse(parsed.result);
                target.toolCalls[tc].isError = r.status === "error" || !!r.error;
              } catch { /* non-JSON, ok */ }
              break;
            }
          }
        }
        // Accumulate insight chips from this tool call
        if (target) {
          if (!accumulatedChips.value[parsed.agentId]) accumulatedChips.value[parsed.agentId] = [];
          accumulatedChips.value[parsed.agentId].push(...buildChipsFromTool(parsed.name, parsed.result, parsed.agentId));
        }
        break;
      }

      case "agent_switch": {
        const parsed = JSON.parse(data);
        const last = messages.value[messages.value.length - 1];
        if (last?.role === "assistant" && !last.done) last.done = true;

        // Assign accumulated chips to the finished agent's last message
        if (last && last.agentId && accumulatedChips.value[last.agentId]?.length) {
          last.insightChips = [...accumulatedChips.value[last.agentId]];
          delete accumulatedChips.value[last.agentId];
        }

        // Track handoff step with per-phase trace_id
        handoffSteps.value.push({
          from: lastAgentId,
          to: parsed.agentId,
          trigger: "",
          traceId: parsed.trace_id || "",
        });
        lastAgentId = parsed.agentId;

        const label = TAG_LABEL[parsed.agentId] || parsed.agentId;
        const verb = AGENT_VERB[parsed.agentId] || "正在处理";
        messages.value.push({
          role: "assistant",
          content: `${label} ${verb}`,
          agentId: parsed.agentId,
          done: true,
          isSwitchBanner: true,
          timestamp: Date.now(),
        });
        messages.value.push({ role: "assistant", content: "", agentId: parsed.agentId, done: false, timestamp: Date.now() });
        scrollBottom();
        break;
      }

      case "warning": {
        try {
          const parsed = JSON.parse(data);
          // Show warning but don't terminate
          if (parsed.message) {
            const last = messages.value[messages.value.length - 1];
            if (last?.role === "assistant" && !last.done) {
              // Append warning as subtle note
            }
          }
        } catch { /* ignore */ }
        break;
      }

      case "verdict": {
        try {
          const parsed = JSON.parse(data);
          currentVerdict.value = parsed.reason || null;
          currentVerdictReason.value = parsed.reason || null;
        } catch { /* ignore */ }
        break;
      }

      case "done": {
        clearStaleTimer();
        const last = messages.value[messages.value.length - 1];
        if (last) {
          last.done = true;
          // Assign remaining accumulated chips to the last agent's message
          if (last.agentId && accumulatedChips.value[last.agentId]?.length) {
            if (!last.insightChips) last.insightChips = [];
            last.insightChips.push(...accumulatedChips.value[last.agentId]);
            delete accumulatedChips.value[last.agentId];
          }
        }
        streaming.value = false;
        resetToolStatus();
        try {
          const parsed = JSON.parse(data);
          // 后补 phase trace_ids：handoffSteps 中缺失 traceId 的步骤用 phase_trace_ids 回填
          if (parsed.phase_trace_ids) {
            for (const step of handoffSteps.value) {
              if (!step.traceId && parsed.phase_trace_ids[step.to]) {
                step.traceId = parsed.phase_trace_ids[step.to];
              }
            }
            // 全局 trace 用第一个 phase 的 trace_id（单 Agent 场景正常显示，多 Agent 场景显示首个）
            const phaseIds = Object.values(parsed.phase_trace_ids) as string[];
            if (phaseIds.length > 0 && !phaseTraceLabel.value) {
              traceId.value = phaseIds[0];
              defaultTraceId.value = phaseIds[0];
            }
          }
        } catch { /* ignore */ }
        abortController = null;
        emit("noteSaved");
        break;
      }

      case "error": {
        clearStaleTimer();
        console.error("SSE error:", data);
        const last = messages.value[messages.value.length - 1];
        if (last) last.done = true;
        streaming.value = false;
        resetToolStatus();
        abortController = null;
        break;
      }
    }
  }

  resetStaleTimer();
  fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input: userInput, session_id: sessionId }),
    signal: abortController.signal,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      const reader = response.body!.getReader();
      await readSSEStream(reader, handleEvent, abortController!.signal);
    })
    .catch((err) => {
      clearStaleTimer();
      if (err.name === "AbortError") return;
      console.error("Stream fetch error:", err);
      const last = messages.value[messages.value.length - 1];
      if (last) last.done = true;
      streaming.value = false;
      resetToolStatus();
      abortController = null;
    });
}

function onInsightChipClick(chip: InsightChipData) {
  // Phase 4: emit to parent for drawer opening
  console.log("Chip clicked:", chip);
}

function abortStream() {
  clearStaleTimer();
  abortController?.abort();
  abortController = null;
  streaming.value = false;
  resetToolStatus();
  const last = messages.value[messages.value.length - 1];
  if (last) last.done = true;
}

function sendWithText(text: string) {
  if (streaming.value) return;
  input.value = text;
  sendMessage();
}

function insertCommand(cmd: string) {
  input.value = cmd.replace("/", "#") + " ";
  nextTick(() => {
    (document.querySelector(".chat-input") as HTMLTextAreaElement)?.focus();
  });
}

// ── 空状态问候 ──
const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 6) return "夜深了";
  if (h < 12) return "早上好";
  if (h < 18) return "下午好";
  return "晚上好";
});

defineExpose({ sendWithText });

onUnmounted(() => {
  clearStaleTimer();
  abortController?.abort();
});
</script>

<template>
  <div class="flex-1 flex flex-col min-h-0">
    <!-- 并行执行状态横幅 -->
    <div
      v-if="streaming && runningAgents.length"
      class="px-4 py-1.5 border-b shrink-0"
      style="background: rgba(124,156,255,0.04); border-color: rgba(124,156,255,0.08)"
    >
      <div class="flex items-center gap-2 text-[11px]">
        <span class="flex gap-1">
          <span
            v-for="(dot, dotIdx) in runningAgents.length"
            :key="dotIdx"
            class="w-1.5 h-1.5 rounded-full animate-pulse-glow"
            :style="{ background: dotIdx === 0 ? 'var(--agent-review)' : 'var(--agent-brain)' }"
          />
        </span>
        <span style="color: var(--text-muted)">{{ runningAgents.join("  ·  ") }}</span>
      </div>
    </div>

    <!-- Stale 看门狗 -->
    <div
      v-if="showStaleWarning && streaming"
      class="px-4 py-2 border-b shrink-0"
      style="background: rgba(255,209,102,0.06); border-color: rgba(255,209,102,0.1)"
    >
      <div class="flex items-center gap-2 text-[11px]" style="color: #FFD166">
        <svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.94-1.24 2.502-2.784a10.5 10.5 0 00-5.864-6.535M12 3.75A10.5 10.5 0 0117.364 18H6.636A10.5 10.5 0 0112 3.75z" />
        </svg>
        <span>连接可能已断开，超过 {{ STALE_TIMEOUT_MS / 1000 }} 秒未收到响应</span>
        <button class="ml-auto underline underline-offset-2 hover:opacity-80" style="color: #FFD166" @click="abortStream">中断重试</button>
      </div>
    </div>

    <!-- 消息列表 -->
    <div ref="messagesEl" class="flex-1 overflow-y-auto px-4 py-3 space-y-4" @scroll="onMessagesScroll">
      <!-- 空状态 -->
      <div v-if="!messages.length" class="flex flex-col items-center justify-center h-full gap-4 text-center">
        <div class="w-12 h-12 rounded-2xl flex items-center justify-center" style="background: rgba(255,255,255,0.02)">
          <svg class="w-6 h-6" style="color: var(--text-muted); opacity: 0.3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
        <div>
          <p class="text-sm font-medium" style="color: var(--text-main)">{{ greeting }}，今天你想捕捉什么？</p>
          <p class="text-xs mt-1" style="color: var(--text-muted)">你可以丢进一个碎片想法，或让 AI 帮你挑战、联想、合成</p>
        </div>
        <div class="flex gap-2">
          <button
            v-for="cmd in COMMANDS"
            :key="cmd.trigger"
            class="text-[11px] px-3 py-1.5 rounded-full border transition-all hover:brightness-110"
            :style="{
              borderColor: cmd.border,
              color: cmd.color,
              background: cmd.bg,
            }"
            @click="insertCommand(cmd.trigger)"
          >{{ cmd.trigger }}</button>
        </div>
      </div>

      <!-- 消息渲染 -->
      <template v-for="(msg, i) in messages" :key="i">
        <!-- Agent 切换分隔条 -->
        <AgentDivider
          v-if="msg.isSwitchBanner"
          :agent-id="msg.agentId || 'knowledge'"
          :label="TAG_LABEL[msg.agentId || ''] || msg.agentId || 'Knowledge'"
          :verb="AGENT_VERB[msg.agentId || ''] || '正在处理'"
          :verdict="i === messages.length - 1 ? currentVerdict : null"
          :verdict-warning="i === messages.length - 1 ? currentVerdictReason : null"
        />

        <!-- 普通消息（文档块风格） -->
        <ThoughtBlock
          v-else
          :role="msg.role"
          :content="msg.content"
          :agent-id="msg.agentId"
          :done="msg.done"
          :insight-chips="msg.insightChips"
          :timestamp="msg.timestamp"
          @chip-click="onInsightChipClick"
        />
      </template>
    </div>

    <!-- 回到底部浮钮 -->
    <div
      v-if="userScrolledUp && streaming"
      class="flex justify-center -mt-2 pb-1 shrink-0"
    >
      <button
        class="px-3 py-1 rounded-full border text-[11px] transition-all hover:brightness-110 flex items-center gap-1"
        style="background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.06); color: var(--text-muted)"
        @click="scrollBottom(true)"
      >
        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7-7-7" />
        </svg>
        回到底部
      </button>
    </div>

    <!-- Agent Trace Bar (collapsed handoff chain) -->
    <AgentTraceBar
      v-if="handoffSteps.length || currentVerdict"
      :steps="handoffSteps"
      :verdict="currentVerdict"
      :verdict-reason="currentVerdictReason"
      @trace-click="onPhaseTraceClick"
    />

    <!-- Trace 摘要条 -->
    <div v-if="traceId" class="px-4 pb-2 shrink-0">
      <!-- 当前在查看 per-phase trace，显示"返回全局" -->
      <div
        v-if="phaseTraceLabel"
        class="flex items-center gap-1 mb-1 text-[10px]"
        style="color: var(--text-muted)"
      >
        <span class="opacity-50">查看 phase</span>
        <span class="font-mono px-1 py-px rounded" style="background: rgba(255,255,255,0.06)">{{ phaseTraceLabel }}</span>
        <button
          class="ml-auto underline underline-offset-2 hover:opacity-80 transition-opacity"
          @click.stop="resetToGlobalTrace"
        >← 回到全局 trace</button>
      </div>
      <div
        class="rounded-lg border overflow-hidden cursor-pointer select-none"
        style="background: rgba(255,255,255,0.02); border-color: var(--border-subtle)"
        @click="toggleTrace"
      >
        <div class="flex items-center gap-2 px-3 py-2 text-[11px]">
          <svg class="w-3 h-3 shrink-0" style="color: var(--text-muted); opacity: 0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <span class="font-mono text-[10px]" style="color: var(--text-muted)">trace {{ traceId.slice(0, 8) }}</span>
          <template v-if="traceData">
            <span style="color: var(--text-muted); opacity: 0.3">·</span>
            <span style="color: var(--text-muted)">{{ traceData.summary.call_count }} calls</span>
            <span style="color: var(--text-muted); opacity: 0.3">·</span>
            <span style="color: var(--text-muted)">{{ traceData.summary.total_tokens.toLocaleString() }} tokens</span>
            <span style="color: var(--text-muted); opacity: 0.3">·</span>
            <span style="color: var(--text-muted)">{{ formatCost(traceData.summary.total_cost_usd) }}</span>
            <span style="color: var(--text-muted); opacity: 0.3">·</span>
            <span style="color: var(--text-muted)">{{ formatMs(traceData.summary.total_latency_ms) }}</span>
          </template>
          <template v-else>
            <span v-if="traceLoading" class="animate-pulse" style="color: var(--text-muted)">loading...</span>
          </template>
          <svg
            class="w-2.5 h-2.5 ml-auto transition-transform shrink-0"
            :class="{ 'rotate-180': traceExpanded }"
            style="color: var(--text-muted); opacity: 0.4"
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </div>

        <!-- 展开详情 -->
        <div v-if="traceExpanded && traceData" class="border-t" style="border-color: var(--border-subtle)">
          <div class="px-3 py-2 space-y-2">
            <div v-for="agent in traceData.agents" :key="agent.agent_id">
              <div class="flex items-center gap-2 text-[10px] px-2 py-1">
                <span
                  class="px-1.5 py-0.5 rounded font-mono text-[9px] shrink-0"
                  :style="{ background: AGENT_TRACE_BG[agent.agent_id] || 'rgba(255,255,255,0.06)', color: AGENT_TRACE_COLOR[agent.agent_id] || '#9AA4B2' }"
                >{{ agent.agent_id }}</span>
                <span style="color: var(--text-muted); opacity: 0.5">{{ agent.subtotal.tokens.toLocaleString() }} tokens</span>
                <span class="ml-auto" style="color: var(--text-muted)">{{ formatMs(agent.subtotal.latency_ms) }}</span>
              </div>
              <div
                v-for="(call, ci) in agent.calls"
                :key="ci"
                class="flex items-center gap-2 text-[10px] py-0.5 pl-8 opacity-70"
              >
                <span class="font-mono text-[9px]" style="color: var(--text-muted)">{{ call.model }}</span>
                <span style="color: var(--text-muted); opacity: 0.5">in:{{ call.input_tokens }} out:{{ call.output_tokens }}</span>
                <span class="ml-auto" style="color: var(--text-muted)">{{ formatMs(call.latency_ms) }}</span>
                <svg
                  v-if="call.status === 'ok'"
                  class="w-3 h-3 shrink-0"
                  style="color: var(--color-success)"
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
                <svg v-else class="w-3 h-3 shrink-0" style="color: var(--color-danger)" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Thought Composer -->
    <ThoughtComposer
      v-model:input="input"
      v-model:streaming="streaming"
      @send="sendMessage"
      @abort="abortStream"
      @insert-command="insertCommand"
    />
  </div>
</template>
