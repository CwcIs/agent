<script setup lang="ts">
import { ref, nextTick, onUnmounted, computed } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";

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
  review: "接手分析",
  brain: "接入联想",
};

const AGENT_ICON: Record<string, string> = {
  review: "R",
  brain: "B",
  knowledge: "K",
};

const AGENT_COLOR: Record<string, string> = {
  review: "amber",
  brain: "purple",
  knowledge: "emerald",
};

function parseTag(text: string): { tag: string; label: string } | null {
  const m = text.match(/#([a-zA-Z][a-zA-Z0-9_-]*)/);
  if (!m) return null;
  const tag = m[1].toLowerCase();
  if (tag in TAG_AGENT_MAP) return { tag, label: TAG_LABEL[tag] };
  return null;
}

marked.setOptions({ breaks: true });

function renderMarkdown(text: string): string {
  const raw = marked.parse(text) as string;
  return DOMPurify.sanitize(raw);
}

interface ToolCall {
  name: string;
  input?: Record<string, unknown>;
  result?: string;
  status: "running" | "done";
  expanded?: boolean;
  isError?: boolean;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  agentId?: string;
  done?: boolean;
  toolCalls?: ToolCall[];
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

// ── / 命令提示 ──
const COMMANDS = [
  { trigger: "/review", label: "Review Agent", desc: "审视你的想法", color: "amber" },
  { trigger: "/brain", label: "Brain Agent", desc: "联想扩展", color: "purple" },
];
const showCommands = computed(() => input.value.startsWith("/") && !input.value.includes(" "));

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

// ── Stale watchdog（审计 A2）──
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

async function fetchTrace() {
  if (!traceId.value || traceLoading.value) return;
  traceLoading.value = true;
  try {
    const res = await fetch(`/trace/${traceId.value}`);
    if (res.ok) traceData.value = await res.json();
  } catch { /* ignore */ }
  finally { traceLoading.value = false; }
}

function toggleTrace() {
  traceExpanded.value = !traceExpanded.value;
  if (traceExpanded.value && !traceData.value) fetchTrace();
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

// 并行执行时各 Agent 的工具调用状态
const agentToolStatus = ref<Record<string, string | null>>({});

const runningAgents = computed(() => {
  return Object.entries(agentToolStatus.value)
    .filter(([, tool]) => tool !== null)
    .map(([agentId, toolName]) => {
      const label = TAG_LABEL[agentId] || agentId;
      return `${label} 正在调用 ${toolName}...`;
    });
});

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
      // sse-starlette 按 RFC 用 \r\n\r\n 分隔事件
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

function sendMessage() {
  if (!input.value.trim() || streaming.value) return;

  const userInput = input.value;
  messages.value.push({ role: "user", content: userInput, done: true, timestamp: Date.now() });
  streaming.value = true;
  traceId.value = null;
  traceData.value = null;
  traceExpanded.value = false;
  input.value = "";
  scrollBottom(true);

  abortController = new AbortController();

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
        break;
      }

      case "agent_switch": {
        const parsed = JSON.parse(data);
        const last = messages.value[messages.value.length - 1];
        if (last?.role === "assistant" && !last.done) last.done = true;
        const label = TAG_LABEL[parsed.agentId] || parsed.agentId;
        const verb = AGENT_VERB[parsed.agentId] || "接管处理";
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

      case "done": {
        clearStaleTimer();
        const last = messages.value[messages.value.length - 1];
        if (last) last.done = true;
        streaming.value = false;
        resetToolStatus();
        try {
          const parsed = JSON.parse(data);
          if (parsed.trace_id) traceId.value = parsed.trace_id;
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

function abortStream() {
  clearStaleTimer();
  abortController?.abort();
  abortController = null;
  streaming.value = false;
  resetToolStatus();
  const last = messages.value[messages.value.length - 1];
  if (last) last.done = true;
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function sendWithText(text: string) {
  if (streaming.value) return;
  input.value = text;
  sendMessage();
}

function copyText(text: string) {
  navigator.clipboard.writeText(text);
}

function insertCommand(cmd: string) {
  input.value = cmd + " ";
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
      class="px-4 py-1.5 bg-indigo-500/5 border-b border-indigo-500/10 shrink-0"
    >
      <div class="flex items-center gap-2 text-[11px]">
        <span class="flex gap-1">
          <span
            v-for="dot in runningAgents.length"
            :key="dot"
            class="w-1.5 h-1.5 rounded-full animate-pulse"
            :class="dot === 1 ? 'bg-amber-400' : 'bg-purple-400'"
          />
        </span>
        <span class="text-gray-400">{{ runningAgents.join('  ·  ') }}</span>
      </div>
    </div>

    <!-- Stale 看门狗警告 -->
    <div
      v-if="showStaleWarning && streaming"
      class="px-4 py-2 bg-amber-500/8 border-b border-amber-500/15 shrink-0"
    >
      <div class="flex items-center gap-2 text-[11px] text-amber-400">
        <svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.94-1.24 2.502-2.784a10.5 10.5 0 00-5.864-6.535M12 3.75A10.5 10.5 0 0117.364 18H6.636A10.5 10.5 0 0112 3.75z" />
        </svg>
        <span>连接可能已断开，超过 {{ STALE_TIMEOUT_MS / 1000 }} 秒未收到响应</span>
        <button class="ml-auto text-amber-500 hover:text-amber-400 underline underline-offset-2" @click="abortStream">中断重试</button>
      </div>
    </div>

    <!-- 消息列表 -->
    <div ref="messagesEl" class="flex-1 overflow-y-auto px-4 py-3 space-y-4" @scroll="onMessagesScroll">
      <!-- 空状态 -->
      <div v-if="!messages.length" class="flex flex-col items-center justify-center h-full gap-4 text-center">
        <div class="w-12 h-12 rounded-2xl bg-white/[0.03] flex items-center justify-center">
          <svg class="w-6 h-6 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
        <div>
          <p class="text-sm text-gray-400 font-medium">{{ greeting }}，有什么想法？</p>
          <p class="text-xs text-gray-600 mt-1">输入碎片，AI 帮你整理成结构化笔记</p>
        </div>
        <div class="flex gap-2">
          <button
            v-for="cmd in COMMANDS"
            :key="cmd.trigger"
            class="text-[11px] px-3 py-1.5 rounded-full border transition-colors"
            :class="[
              cmd.color === 'amber'
                ? 'border-amber-500/20 text-amber-400 hover:bg-amber-500/10'
                : 'border-purple-500/20 text-purple-400 hover:bg-purple-500/10'
            ]"
            @click="insertCommand(cmd.trigger)"
          >{{ cmd.trigger }}</button>
        </div>
      </div>

      <!-- 消息气泡 -->
      <template v-for="(msg, i) in messages" :key="i">
        <!-- Agent 切换分隔条 -->
        <div
          v-if="msg.isSwitchBanner"
          class="flex items-center gap-2 py-1.5 max-w-[72%] mx-auto"
        >
          <div class="flex-1 h-px bg-gradient-to-r from-transparent via-white/[0.06] to-transparent" />
          <span
            :class="[
              'text-[10px] font-medium px-2 py-0.5 rounded-full shrink-0',
              msg.agentId === 'review'
                ? 'bg-amber-500/10 text-amber-400 border border-amber-500/15'
                : msg.agentId === 'brain'
                  ? 'bg-purple-500/10 text-purple-400 border border-purple-500/15'
                  : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/15'
            ]"
          >{{ msg.content }}</span>
          <div class="flex-1 h-px bg-gradient-to-l from-transparent via-white/[0.06] to-transparent" />
        </div>

        <!-- 普通气泡 -->
        <div
          v-else
          :class="['flex gap-2.5 group', msg.role === 'user' ? 'flex-row-reverse' : 'flex-row']"
        >
          <!-- 头像 -->
          <div
            v-if="msg.role === 'assistant' && !msg.isSwitchBanner"
            :class="[
              'w-7 h-7 rounded-lg shrink-0 flex items-center justify-center text-[10px] font-semibold mt-0.5',
              msg.agentId === 'review'
                ? 'bg-amber-500/15 text-amber-400'
                : msg.agentId === 'brain'
                  ? 'bg-purple-500/15 text-purple-400'
                  : 'bg-emerald-500/15 text-emerald-400'
            ]"
          >
            {{ AGENT_ICON[msg.agentId || 'knowledge'] || 'K' }}
          </div>

          <!-- 气泡 -->
          <div
            :class="[
              'rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed relative',
              msg.role === 'user'
                ? 'bg-indigo-600/80 text-white rounded-tr-sm max-w-[72%]'
                : 'max-w-[80%] rounded-tl-sm',
              msg.role === 'assistant' && !msg.isSwitchBanner
                ? 'bg-white/[0.03] text-gray-200 border border-white/[0.05]'
                : '',
            ]"
          >
            <!-- Agent 名 + 时间 -->
            <div v-if="msg.agentId && !msg.isSwitchBanner" class="flex items-center gap-2 mb-1">
              <span
                :class="[
                  'text-[10px] font-medium',
                  msg.agentId === 'review' ? 'text-amber-500' : msg.agentId === 'brain' ? 'text-purple-500' : 'text-emerald-500'
                ]"
              >{{ TAG_LABEL[msg.agentId] || msg.agentId }}</span>
            </div>

            <!-- 内容 -->
            <div v-if="msg.role === 'assistant'" class="prose prose-invert prose-sm max-w-none">
              <span v-html="renderMarkdown(msg.content)"></span>
              <span v-if="!msg.done" class="inline-block w-0.5 h-3.5 bg-gray-400 ml-0.5 animate-pulse align-text-bottom"></span>
            </div>
            <div v-else class="whitespace-pre-wrap">{{ msg.content }}</div>

            <!-- 时间戳 hover 显示 -->
            <div
              class="absolute -bottom-5 text-[9px] text-gray-700 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
              :class="msg.role === 'user' ? 'right-0' : 'left-0'"
            >{{ formatTime(msg.timestamp) }}</div>

            <!-- 工具调用内联卡片 -->
            <div v-if="msg.toolCalls?.length" class="mt-2.5 space-y-1.5">
              <div
                v-for="(tc, ti) in msg.toolCalls"
                :key="ti"
                class="rounded-lg border overflow-hidden transition-colors"
                :class="[
                  tc.isError
                    ? 'border-red-500/15 bg-red-500/[0.03]'
                    : tc.status === 'running'
                      ? 'border-indigo-500/15 bg-indigo-500/[0.03]'
                      : 'border-emerald-500/10 bg-emerald-500/[0.02]'
                ]"
              >
                <div
                  class="flex items-center gap-2 px-2.5 py-2 cursor-pointer select-none"
                  @click="tc.expanded = !tc.expanded"
                >
                  <!-- 状态图标 -->
                  <svg
                    v-if="tc.status === 'running'"
                    class="w-3 h-3 text-indigo-400 animate-spin shrink-0"
                    fill="none" viewBox="0 0 24 24"
                  >
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <svg
                    v-else-if="tc.isError"
                    class="w-3 h-3 text-red-400 shrink-0"
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  <svg
                    v-else
                    class="w-3 h-3 text-emerald-400 shrink-0"
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                  <span class="text-[11px] text-gray-400 font-mono">{{ tc.name }}</span>
                  <span v-if="tc.status === 'running'" class="text-[9px] text-indigo-500 animate-pulse">执行中</span>
                  <span v-else-if="tc.isError" class="text-[9px] text-red-500">失败</span>
                  <span v-else class="text-[9px] text-emerald-600">完成</span>
                  <svg
                    class="w-2.5 h-2.5 text-gray-700 ml-auto transition-transform shrink-0"
                    :class="{ 'rotate-180': tc.expanded }"
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
                <!-- 展开内容 -->
                <div v-if="tc.expanded" class="px-2.5 pb-2.5 space-y-2">
                  <div v-if="tc.input && Object.keys(tc.input).length" class="text-[10px]">
                    <span class="text-gray-600 font-medium">输入</span>
                    <pre class="mt-1 text-gray-500 bg-black/20 rounded-lg p-2 overflow-x-auto max-h-24">{{ JSON.stringify(tc.input, null, 2) }}</pre>
                  </div>
                  <div v-if="tc.result" class="text-[10px]">
                    <div class="flex items-center gap-2">
                      <span class="text-gray-600 font-medium">结果</span>
                      <button
                        class="text-[9px] px-1.5 py-0.5 rounded bg-white/[0.04] hover:bg-white/[0.08] text-gray-500 hover:text-gray-300 transition-colors"
                        @click.stop="copyText(tc.result)"
                      >复制</button>
                    </div>
                    <pre
                      class="mt-1 text-gray-400 bg-black/20 rounded-lg p-2 overflow-x-auto max-h-32"
                      :class="tc.isError ? 'text-red-300' : 'text-gray-400'"
                    >{{ tc.result.length > 2000 ? tc.result.slice(0, 2000) + '\n…(已截断)' : tc.result }}</pre>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 用户头像占位 -->
          <div
            v-if="msg.role === 'user'"
            class="w-7 h-7 rounded-lg bg-indigo-500/15 shrink-0 flex items-center justify-center text-[10px] font-semibold text-indigo-400 mt-0.5"
          >U</div>
        </div>
      </template>
    </div>

    <!-- 回到底部浮钮 -->
    <div
      v-if="userScrolledUp && streaming"
      class="flex justify-center -mt-2 pb-1 shrink-0"
    >
      <button
        class="px-3 py-1 rounded-full bg-white/10 hover:bg-white/15 border border-white/[0.08] text-[11px] text-gray-400 hover:text-gray-200 transition-colors flex items-center gap-1"
        @click="scrollBottom(true)"
      >
        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7-7-7" />
        </svg>
        回到底部
      </button>
    </div>

    <!-- Trace 摘要条 -->
    <div v-if="traceId" class="px-4 pb-2 shrink-0">
      <div
        class="rounded-lg border border-white/[0.06] bg-white/[0.02] overflow-hidden cursor-pointer select-none"
        @click="toggleTrace"
      >
        <div class="flex items-center gap-2 px-3 py-2 text-[11px]">
          <svg class="w-3 h-3 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <span class="text-gray-500 font-mono text-[10px]">trace {{ traceId.slice(0, 8) }}</span>
          <template v-if="traceData">
            <span class="text-gray-700">·</span>
            <span class="text-gray-400">{{ traceData.summary.call_count }} calls</span>
            <span class="text-gray-700">·</span>
            <span class="text-gray-400">{{ traceData.summary.total_tokens.toLocaleString() }} tokens</span>
            <span class="text-gray-700">·</span>
            <span class="text-gray-400">{{ formatCost(traceData.summary.total_cost_usd) }}</span>
            <span class="text-gray-700">·</span>
            <span class="text-gray-400">{{ formatMs(traceData.summary.total_latency_ms) }}</span>
          </template>
          <template v-else>
            <span v-if="traceLoading" class="text-gray-700 animate-pulse">loading...</span>
          </template>
          <svg
            class="w-2.5 h-2.5 text-gray-700 ml-auto transition-transform shrink-0"
            :class="{ 'rotate-180': traceExpanded }"
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </div>

        <!-- 展开详情 -->
        <div v-if="traceExpanded && traceData" class="border-t border-white/[0.06]">
          <div class="px-3 py-2 space-y-2">
            <div v-for="agent in traceData.agents" :key="agent.agent_id">
              <div class="flex items-center gap-2 text-[10px] px-2 py-1">
                <span :class="[
                  'px-1.5 py-0.5 rounded font-mono text-[9px] shrink-0',
                  agent.agent_id === 'review'
                    ? 'bg-amber-500/10 text-amber-400'
                    : agent.agent_id === 'brain'
                      ? 'bg-purple-500/10 text-purple-400'
                      : 'bg-emerald-500/10 text-emerald-400'
                ]">{{ agent.agent_id }}</span>
                <span class="text-gray-600">{{ agent.subtotal.tokens.toLocaleString() }} tokens</span>
                <span class="text-gray-500 ml-auto">{{ formatMs(agent.subtotal.latency_ms) }}</span>
              </div>
              <div
                v-for="(call, ci) in agent.calls"
                :key="ci"
                class="flex items-center gap-2 text-[10px] py-0.5 pl-8 opacity-70"
              >
                <span class="text-gray-500 font-mono text-[9px]">{{ call.model }}</span>
                <span class="text-gray-600">in:{{ call.input_tokens }} out:{{ call.output_tokens }}</span>
                <span class="text-gray-500 ml-auto">{{ formatMs(call.latency_ms) }}</span>
                <svg
                  v-if="call.status === 'ok'"
                  class="w-3 h-3 text-emerald-500 shrink-0"
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
                <svg v-else class="w-3 h-3 text-red-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="px-4 pb-4 shrink-0 relative">
      <!-- / 命令面板 -->
      <div
        v-if="showCommands && input.length >= 1"
        class="absolute bottom-full left-4 right-4 mb-2 bg-[#1a1a1a] border border-white/[0.08] rounded-xl shadow-2xl overflow-hidden z-10"
      >
        <div class="px-3 py-1.5 text-[10px] text-gray-600 border-b border-white/[0.06]">命令</div>
        <button
          v-for="cmd in COMMANDS"
          :key="cmd.trigger"
          class="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-white/[0.04] transition-colors text-left"
          :class="input === cmd.trigger ? 'opacity-100' : 'opacity-60'"
          @click="insertCommand(cmd.trigger)"
        >
          <span
            class="w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold shrink-0"
            :class="cmd.color === 'amber' ? 'bg-amber-500/15 text-amber-400' : 'bg-purple-500/15 text-purple-400'"
          >/</span>
          <div>
            <span class="text-xs text-gray-300">{{ cmd.trigger }}</span>
            <span class="text-[10px] text-gray-600 ml-1.5">{{ cmd.desc }}</span>
          </div>
        </button>
      </div>

      <!-- tag pill -->
      <div v-if="activeTag" class="mb-1.5 flex items-center gap-1.5 px-1">
        <span class="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/20">
          <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
          → {{ activeTag.label }}
        </span>
      </div>

      <div
        class="flex items-end gap-2 bg-white/[0.04] border border-white/[0.08] rounded-2xl p-2 focus-within:border-white/20 transition-colors"
        :class="[activeTag ? 'border-amber-500/20' : '', showCommands ? 'border-indigo-500/30' : '']"
      >
        <textarea
          v-model="input"
          class="chat-input flex-1 bg-transparent text-sm text-gray-200 placeholder-gray-600 resize-none outline-none leading-relaxed min-h-[40px] max-h-32 px-2 py-1.5"
          :placeholder="activeTag ? `#${activeTag.tag} 已激活…` : '输入碎片想法，#review / #brain 触发 Agent，/ 查看命令'"
          rows="1"
          @keydown="handleKeydown"
          @input="($event.target as HTMLTextAreaElement).style.height = 'auto'; ($event.target as HTMLTextAreaElement).style.height = ($event.target as HTMLTextAreaElement).scrollHeight + 'px'"
        />
        <button
          v-if="!streaming"
          :disabled="!input.trim()"
          class="w-8 h-8 rounded-xl flex items-center justify-center transition-all shrink-0"
          :class="input.trim() ? 'bg-indigo-600 hover:bg-indigo-500 text-white' : 'bg-white/5 text-gray-600 cursor-not-allowed'"
          @click="sendMessage"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </button>
        <button
          v-else
          class="w-8 h-8 rounded-xl bg-red-500/20 hover:bg-red-500/30 text-red-400 flex items-center justify-center transition-all shrink-0"
          @click="abortStream"
        >
          <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
            <rect x="6" y="6" width="12" height="12" rx="1" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>
