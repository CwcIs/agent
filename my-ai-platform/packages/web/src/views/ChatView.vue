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
}

interface Message {
  role: "user" | "assistant";
  content: string;
  agentId?: string;
  done?: boolean;
  toolCalls?: ToolCall[];
  isSwitchBanner?: boolean;
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
let eventSource: EventSource | null = null;

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

const AGENT_DISPLAY: Record<string, string> = { knowledge: "Knowledge Agent", review: "Review Agent", brain: "Brain Agent" };
function agentBadgeClass(agentId: string): string {
  const base = 'px-1.5 py-0.5 rounded font-mono text-[10px] shrink-0 min-w-[64px] text-center';
  if (agentId === 'review') return base + ' bg-amber-500/10 text-amber-400';
  if (agentId === 'brain')  return base + ' bg-purple-500/10 text-purple-400';
  return base + ' bg-emerald-500/10 text-emerald-400';
}
function formatMs(ms: number): string {
  if (ms >= 1000) return (ms / 1000).toFixed(1) + "s";
  return ms + "ms";
}
function formatCost(usd: number): string {
  return "$" + usd.toFixed(4);
}

// 并行执行时各 Agent 的工具调用状态（agentId → 当前工具名）
const agentToolStatus = ref<Record<string, string | null>>({});

const runningAgents = computed(() => {
  return Object.entries(agentToolStatus.value)
    .filter(([, tool]) => tool !== null)
    .map(([agentId, toolName]) => {
      const label = TAG_LABEL[agentId] || agentId;
      return `${label} 正在调用 ${toolName}...`;
    });
});

async function scrollBottom() {
  await nextTick();
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
  }
}

function resetToolStatus() {
  agentToolStatus.value = {};
}

function sendMessage() {
  if (!input.value.trim() || streaming.value) return;

  messages.value.push({ role: "user", content: input.value, done: true });
  streaming.value = true;
  traceId.value = null;
  traceData.value = null;
  traceExpanded.value = false;
  scrollBottom();

  const encoded = encodeURIComponent(input.value);
  eventSource = new EventSource(`/chat/stream?input=${encoded}&session_id=${sessionId}`);

  eventSource.addEventListener("token", (e) => {
    const data = JSON.parse(e.data);
    // 倒序查找该 agent 最近一条未完成的气泡（支持并行 fan-out interleaved 事件）
    let target: Message | null = null;
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const m = messages.value[i];
      if (m.role === "assistant" && !m.done && m.agentId === data.agentId && !m.isSwitchBanner) {
        target = m;
        break;
      }
    }
    if (target) {
      target.content += data.delta;
    } else {
      messages.value.push({ role: "assistant", content: data.delta, agentId: data.agentId, done: false });
    }
    scrollBottom();
  });

  eventSource.addEventListener("tool_start", (e) => {
    const data = JSON.parse(e.data);
    // data: { name, input, agentId }
    agentToolStatus.value[data.agentId] = data.name;

    // 倒序查找该 agent 的未完成气泡
    let target: Message | null = null;
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const m = messages.value[i];
      if (m.role === "assistant" && !m.done && m.agentId === data.agentId && !m.isSwitchBanner) {
        target = m;
        break;
      }
    }
    if (target) {
      if (!target.toolCalls) target.toolCalls = [];
      target.toolCalls.push({
        name: data.name,
        input: data.input,
        status: "running",
      });
    }
  });

  eventSource.addEventListener("tool_end", (e) => {
    const data = JSON.parse(e.data);
    // data: { name, result, agentId }
    agentToolStatus.value[data.agentId] = null;

    let target: Message | null = null;
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const m = messages.value[i];
      if (m.role === "assistant" && !m.done && m.agentId === data.agentId && !m.isSwitchBanner) {
        target = m;
        break;
      }
    }
    if (target?.toolCalls) {
      for (let tc = target.toolCalls.length - 1; tc >= 0; tc--) {
        if (target.toolCalls[tc].name === data.name && target.toolCalls[tc].status === "running") {
          target.toolCalls[tc].result = data.result;
          target.toolCalls[tc].status = "done";
          break;
        }
      }
    }
  });

  eventSource.addEventListener("agent_switch", (e) => {
    const data = JSON.parse(e.data);
    // 关闭上一条消息
    const last = messages.value[messages.value.length - 1];
    if (last?.role === "assistant" && !last.done) last.done = true;

    const label = TAG_LABEL[data.agentId] || data.agentId;
    const verb = AGENT_VERB[data.agentId] || "接管处理";

    // 插入切换分隔条
    messages.value.push({
      role: "assistant",
      content: `→ ${label} ${verb}`,
      agentId: data.agentId,
      done: true,
      isSwitchBanner: true,
    });

    // 再创建接收 token 的空气泡
    messages.value.push({ role: "assistant", content: "", agentId: data.agentId, done: false });
    scrollBottom();
  });

  eventSource.addEventListener("done", (e) => {
    const last = messages.value[messages.value.length - 1];
    if (last) last.done = true;
    streaming.value = false;
    resetToolStatus();
    try {
      const data = JSON.parse(e.data);
      if (data.trace_id) traceId.value = data.trace_id;
    } catch { /* ignore */ }
    eventSource?.close();
    emit("noteSaved");
  });

  eventSource.onerror = () => {
    const last = messages.value[messages.value.length - 1];
    if (last) last.done = true;
    streaming.value = false;
    resetToolStatus();
    eventSource?.close();
  };

  input.value = "";
}

function abortStream() {
  eventSource?.close();
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

defineExpose({ sendWithText });

onUnmounted(() => {
  eventSource?.close();
});
</script>

<template>
  <div class="flex-1 flex flex-col min-h-0">
    <!-- 并行执行状态横幅 -->
    <div
      v-if="streaming && runningAgents.length"
      class="px-5 py-2 bg-indigo-500/5 border-b border-indigo-500/10 shrink-0"
    >
      <div class="flex items-center gap-2 text-xs">
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

    <!-- 消息列表 -->
    <div ref="messagesEl" class="flex-1 overflow-y-auto px-5 py-4 space-y-5">
      <!-- 空状态 -->
      <div v-if="!messages.length" class="flex flex-col items-center justify-center h-full gap-3 text-center">
        <div class="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center">
          <svg class="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
        <p class="text-sm text-gray-500">输入碎片想法，AI 帮你整理成结构化笔记</p>
        <p class="text-xs text-gray-700">⏎ 发送 · Shift+⏎ 换行</p>
      </div>

      <!-- 消息气泡 -->
      <template v-for="(msg, i) in messages" :key="i">
        <!-- Agent 切换分隔条 -->
        <div
          v-if="msg.isSwitchBanner"
          class="flex items-center gap-2 py-1.5 px-3 my-1 max-w-[72%] mx-auto"
        >
          <div class="flex-1 h-px bg-white/[0.06]" />
          <span
            :class="[
              'text-[11px] font-medium px-2 py-0.5 rounded-full shrink-0',
              msg.agentId === 'review'
                ? 'bg-amber-500/10 text-amber-400 border border-amber-500/15'
                : msg.agentId === 'brain'
                  ? 'bg-purple-500/10 text-purple-400 border border-purple-500/15'
                  : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/15'
            ]"
          >{{ msg.content }}</span>
          <div class="flex-1 h-px bg-white/[0.06]" />
        </div>

        <!-- 普通气泡 -->
        <div
          v-else
          :class="['flex gap-3', msg.role === 'user' ? 'flex-row-reverse' : 'flex-row']"
        >
          <!-- 头像 -->
          <div
            :class="[
              'w-7 h-7 rounded-lg shrink-0 flex items-center justify-center text-xs font-semibold mt-0.5',
              msg.role === 'user'
                ? 'bg-indigo-500/20 text-indigo-400'
                : msg.agentId === 'review'
                  ? 'bg-amber-500/20 text-amber-400'
                  : msg.agentId === 'brain'
                    ? 'bg-purple-500/20 text-purple-400'
                    : 'bg-emerald-500/20 text-emerald-400'
            ]"
          >
            {{ msg.role === 'user' ? 'U' : (msg.agentId === 'review' ? 'R' : msg.agentId === 'brain' ? 'B' : 'K') }}
          </div>

          <!-- 气泡 -->
          <div
            :class="[
              'max-w-[72%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
              msg.role === 'user'
                ? 'bg-indigo-600/80 text-white rounded-tr-sm'
                : 'bg-white/[0.06] text-gray-200 rounded-tl-sm border border-white/[0.06]'
            ]"
          >
            <div
              v-if="msg.agentId"
              :class="[
                'text-[10px] mb-1 font-mono',
                msg.agentId === 'review' ? 'text-amber-500' : msg.agentId === 'brain' ? 'text-purple-500' : 'text-emerald-600'
              ]"
            >{{ msg.agentId }}</div>
            <div v-if="msg.role === 'assistant'" class="prose prose-invert prose-sm max-w-none">
              <span v-html="renderMarkdown(msg.content)"></span>
              <span v-if="!msg.done" class="inline-block w-0.5 h-3.5 bg-gray-400 ml-0.5 animate-pulse align-text-bottom"></span>
            </div>
            <div v-else class="whitespace-pre-wrap">{{ msg.content }}</div>

            <!-- 工具调用内联卡片 -->
            <div v-if="msg.toolCalls?.length" class="mt-2 space-y-1.5">
              <div
                v-for="(tc, ti) in msg.toolCalls"
                :key="ti"
                class="rounded-lg border border-white/[0.06] bg-white/[0.02] overflow-hidden"
              >
                <div
                  class="flex items-center gap-1.5 px-2.5 py-1.5 cursor-pointer select-none"
                  @click="tc.expanded = !tc.expanded"
                >
                  <!-- running 时旋转动画，done 时勾号 -->
                  <svg
                    v-if="tc.status === 'running'"
                    class="w-3 h-3 text-indigo-400 animate-spin shrink-0"
                    fill="none" viewBox="0 0 24 24"
                  >
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <svg
                    v-else
                    class="w-3 h-3 text-emerald-500 shrink-0"
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                  <span class="text-[11px] text-gray-500 font-mono">{{ tc.name }}</span>
                  <svg
                    class="w-2.5 h-2.5 text-gray-700 ml-auto transition-transform shrink-0"
                    :class="{ 'rotate-180': tc.expanded }"
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
                <!-- 展开内容 -->
                <div v-if="tc.expanded" class="px-2.5 pb-2 space-y-1.5">
                  <div v-if="tc.input && Object.keys(tc.input).length" class="text-[10px]">
                    <span class="text-gray-600">输入:</span>
                    <pre class="mt-0.5 text-gray-500 bg-white/[0.03] rounded p-1.5 overflow-x-auto max-h-20">{{ JSON.stringify(tc.input, null, 2) }}</pre>
                  </div>
                  <div v-if="tc.result" class="text-[10px]">
                    <span class="text-gray-600">结果:</span>
                    <pre class="mt-0.5 text-gray-400 bg-white/[0.03] rounded p-1.5 overflow-x-auto max-h-24">{{ tc.result }}</pre>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Trace 摘要条 -->
    <div
      v-if="traceId"
      class="px-5 pb-2 shrink-0"
    >
      <div
        class="rounded-lg border border-white/[0.06] bg-white/[0.02] overflow-hidden cursor-pointer select-none"
        @click="toggleTrace"
      >
        <div class="flex items-center gap-2 px-3 py-2 text-xs">
          <svg class="w-3 h-3 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <span class="text-gray-500 font-mono text-[11px]">trace {{ traceId.slice(0, 8) }}</span>
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

        <!-- 展开详情：按 Agent 分组 -->
        <div v-if="traceExpanded && traceData" class="border-t border-white/[0.06]">
          <div class="px-3 py-2 space-y-2">
            <div v-for="agent in traceData.agents" :key="agent.agent_id">
              <!-- Agent 汇总行 -->
              <div class="flex items-center gap-2 text-[11px] px-2 py-1">
                <span :class="agentBadgeClass(agent.agent_id)">{{ agent.agent_id }}</span>
                <span class="text-gray-600">{{ agent.subtotal.tokens.toLocaleString() }} tokens</span>
                <span class="text-gray-500 ml-auto">{{ formatMs(agent.subtotal.latency_ms) }}</span>
              </div>
              <!-- call 明细（缩进） -->
              <div
                v-for="(call, ci) in agent.calls"
                :key="ci"
                class="flex items-center gap-2 text-[11px] py-0.5 pl-8 opacity-70"
              >
                <span class="text-gray-500 font-mono text-[10px]">{{ call.model }}</span>
                <span class="text-gray-600">in:{{ call.input_tokens }} out:{{ call.output_tokens }}</span>
                <span class="text-gray-500 ml-auto">{{ formatMs(call.latency_ms) }}</span>
                <svg
                  v-if="call.status === 'ok'"
                  class="w-3 h-3 text-emerald-500 shrink-0"
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
                <svg
                  v-else
                  class="w-3 h-3 text-red-400 shrink-0"
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="px-4 pb-4 shrink-0">
      <!-- tag pill -->
      <div v-if="activeTag" class="mb-1.5 flex items-center gap-1.5 px-1">
        <span class="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/20">
          <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
          → {{ activeTag.label }}
        </span>
      </div>
      <div class="flex items-end gap-2 bg-white/[0.04] border border-white/[0.08] rounded-2xl p-2 focus-within:border-white/20 transition-colors" :class="activeTag ? 'border-amber-500/20' : ''">
        <textarea
          v-model="input"
          class="flex-1 bg-transparent text-sm text-gray-200 placeholder-gray-600 resize-none outline-none leading-relaxed min-h-[40px] max-h-32 px-2 py-1.5"
          :placeholder="activeTag ? `#${activeTag.tag} 已激活，直接输入内容...` : '输入碎片想法，或用 #review / #brain 触发 Agent'"
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
