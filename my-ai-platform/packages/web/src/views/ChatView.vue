<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted, computed, watch } from "vue";
import AgentDivider from "../components/AgentDivider.vue";
import AgentTraceBar from "../components/AgentTraceBar.vue";
import ChatTracePanel from "../components/ChatTracePanel.vue";
import RunApprovalCard from "../components/RunApprovalCard.vue";
import ThoughtBlock from "../components/ThoughtBlock.vue";
import type { InsightChipData } from "../components/InsightChip.vue";
import ThoughtComposer from "../components/ThoughtComposer.vue";
import {
  AGENT_VERB,
  COMMANDS,
  TAG_LABEL,
  buildChipsFromTool,
  parseTag,
} from "../chat/model";
import type { HandoffStep, Message } from "../chat/model";
import { readSSEStream } from "../chat/sse";
import { useChatTrace } from "../composables/useChatTrace";

const props = defineProps<{ sessionId: string }>();
const emit = defineEmits<{
  noteSaved: [];
  traceInspect: [traceId: string];
  conversationUpdated: [];
  statusChange: [status: { streaming: boolean; runningAgents: string[] }];
}>();
const {
  traceId,
  traceExpanded,
  traceData,
  traceLoading,
  phaseTraceLabel,
  toggleTrace,
  setActiveTrace,
  onPhaseTraceClick,
  resetToGlobalTrace,
  resetTrace,
} = useChatTrace();

const messages = ref<Message[]>([]);
const input = ref("");
const streaming = ref(false);
const resolvingApproval = ref(false);
const pendingApproval = ref<null | {
  runId: string;
  approvalId: string;
  targetAgent: string;
  risk: string;
  reason: string;
}>(null);
const activeTag = computed(() => parseTag(input.value));
const messagesEl = ref<HTMLElement | null>(null);

let abortController: AbortController | null = null;
let activeEventHandler: ((eventType: string, data: string) => void) | null = null;
let historyRequest = 0;

async function loadHistory(sessionId: string) {
  const requestId = ++historyRequest;
  abortStream();
  messages.value = [];
  handoffSteps.value = [];
  currentVerdict.value = null;
  currentVerdictReason.value = null;
  pendingApproval.value = null;
  resetTrace();
  try {
    const response = await fetch(`/chat/history?session_id=${encodeURIComponent(sessionId)}`);
    if (!response.ok || requestId !== historyRequest) return;
    const data = await response.json();
    let previousAgent = "";
    const restored: Message[] = [];
    for (const item of data.messages || []) {
      const agentId = item.role === "assistant" ? (item.agent_id || "knowledge") : undefined;
      const timestamp = new Date(item.created_at.replace(" ", "T")).getTime();
      if (agentId && previousAgent && agentId !== previousAgent) {
        restored.push({
          role: "assistant",
          content: "",
          agentId,
          done: true,
          isSwitchBanner: true,
          timestamp,
        });
      }
      restored.push({
        role: item.role,
        content: item.content,
        agentId,
        done: true,
        timestamp,
      });
      if (agentId) previousAgent = agentId;
    }
    messages.value = restored;
    await scrollBottom(true);
  } catch {
    if (requestId === historyRequest) messages.value = [];
  }
}

// 鈹€鈹€ 鏅鸿兘婊氬姩 鈹€鈹€
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

// 鈹€鈹€ Stale watchdog 鈹€鈹€
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

// 鈹€鈹€ 骞惰 Agent 鐘舵€?鈹€鈹€
const agentToolStatus = ref<Record<string, string | null>>({});

// 鈹€鈹€ Insight Chips 绱Н 鈹€鈹€
const accumulatedChips = ref<Record<string, InsightChipData[]>>({});

const runningAgents = computed(() => {
  return Object.entries(agentToolStatus.value)
    .filter(([, tool]) => tool !== null)
    .map(([agentId, toolName]) => {
      const label = TAG_LABEL[agentId] || agentId;
      return `${label} 正在调用 ${toolName}...`;
    });
});

// 鈹€鈹€ Handoff Chain 杩借釜 鈹€鈹€
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

// 鈹€鈹€ 鍙戦€?鈹€鈹€
function sendMessage() {
  if (!input.value.trim() || streaming.value) return;

  const userInput = input.value;
  messages.value.push({ role: "user", content: userInput, done: true, timestamp: Date.now() });
  streaming.value = true;
  resetTrace();
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

      case "approval_required": {
        const parsed = JSON.parse(data);
        clearStaleTimer();
        pendingApproval.value = {
          runId: parsed.run_id,
          approvalId: parsed.approval_id,
          targetAgent: parsed.target_agent,
          risk: parsed.risk,
          reason: parsed.reason,
        };
        streaming.value = false;
        abortController = null;
        break;
      }

      case "approval_resolved": {
        pendingApproval.value = null;
        resolvingApproval.value = false;
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
          // 鍚庤ˉ phase trace_ids锛歨andoffSteps 涓己澶?traceId 鐨勬楠ょ敤 phase_trace_ids 鍥炲～
          if (parsed.phase_trace_ids) {
            for (const step of handoffSteps.value) {
              if (!step.traceId && parsed.phase_trace_ids[step.to]) {
                step.traceId = parsed.phase_trace_ids[step.to];
              }
            }
            const phaseIds = Object.values(parsed.phase_trace_ids) as string[];
            if (phaseIds.length > 0 && !phaseTraceLabel.value) {
              setActiveTrace(phaseIds[0]);
            }
          } else if (parsed.trace_id) {
            setActiveTrace(parsed.trace_id);
          }
        } catch { /* ignore */ }
        abortController = null;
        emit("noteSaved");
        emit("conversationUpdated");
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

  activeEventHandler = handleEvent;

  resetStaleTimer();
  fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input: userInput, session_id: props.sessionId }),
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

async function resolveApproval(approved: boolean) {
  const approval = pendingApproval.value;
  if (!approval || resolvingApproval.value) return;
  resolvingApproval.value = true;
  streaming.value = true;
  abortController = new AbortController();
  try {
    const response = await fetch(
      `/runs/${encodeURIComponent(approval.runId)}/approvals/${encodeURIComponent(approval.approvalId)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved }),
        signal: abortController.signal,
      },
    );
    if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
    if (!activeEventHandler) throw new Error("missing active run event handler");
    await readSSEStream(response.body.getReader(), activeEventHandler, abortController.signal);
  } catch (error) {
    if (!(error instanceof DOMException && error.name === "AbortError")) {
      console.error("Approval resume failed:", error);
    }
    streaming.value = false;
    resolvingApproval.value = false;
  }
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

// 鈹€鈹€ 绌虹姸鎬侀棶鍊?鈹€鈹€
const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 6) return "夜深了";
  if (h < 12) return "早上好";
  if (h < 18) return "下午好";
  return "晚上好";
});

defineExpose({ sendWithText });

onMounted(() => loadHistory(props.sessionId));
watch(() => props.sessionId, sessionId => loadHistory(sessionId));
watch(
  [streaming, runningAgents],
  () => emit("statusChange", { streaming: streaming.value, runningAgents: runningAgents.value }),
  { immediate: true, deep: true },
);

onUnmounted(() => {
  clearStaleTimer();
  abortController?.abort();
});
</script>
<template>
  <div class="chat-studio">
    <div v-if="streaming && runningAgents.length" class="agent-activity">
      <span class="activity-dots">
        <i v-for="(_, dotIdx) in runningAgents" :key="dotIdx" :style="{ background: dotIdx === 0 ? 'var(--agent-review)' : 'var(--agent-brain)' }" />
      </span>
      <span>{{ runningAgents.join(" · ") }}</span>
    </div>

    <div v-if="showStaleWarning && streaming" class="stale-warning">
      <span>连接可能已断开，超过 {{ STALE_TIMEOUT_MS / 1000 }} 秒没有收到响应</span>
      <button @click="abortStream">停止并重试</button>
    </div>

    <div ref="messagesEl" class="message-canvas" @scroll="onMessagesScroll">
      <section v-if="!messages.length" class="empty-hero">
        <div class="empty-heading">
          <span class="empty-mark">N</span>
          <div>
            <p class="hero-kicker">New isolated task</p>
            <h1>{{ greeting }}，从一个问题开始</h1>
          </div>
        </div>
        <p class="hero-copy">这个任务有独立上下文。直接记录想法，或明确指定一位 Agent 开始。</p>
        <div class="hero-actions">
          <button @click="input = '@knowledge '">
            <b class="knowledge">K</b><span><strong>@knowledge</strong><small>整理与检索</small></span>
          </button>
          <button @click="input = '@review '">
            <b class="review">R</b><span><strong>@review</strong><small>挑战假设</small></span>
          </button>
          <button @click="input = '@brain '">
            <b class="brain">B</b><span><strong>@brain</strong><small>联想扩展</small></span>
          </button>
        </div>
        <div class="task-hints">
          <span>常用入口</span>
          <button v-for="cmd in COMMANDS" :key="cmd.trigger" @click="insertCommand(cmd.trigger)">
            {{ cmd.trigger }} {{ cmd.desc }}
          </button>
        </div>
      </section>

      <template v-for="(msg, i) in messages" :key="i">
        <AgentDivider
          v-if="msg.isSwitchBanner"
          :agent-id="msg.agentId || 'knowledge'"
          :label="TAG_LABEL[msg.agentId || ''] || msg.agentId || 'Knowledge'"
          :verb="AGENT_VERB[msg.agentId || ''] || '正在处理'"
          :verdict="i === messages.length - 1 ? currentVerdict : null"
          :verdict-warning="i === messages.length - 1 ? currentVerdictReason : null"
        />
        <ThoughtBlock
          v-else
          :role="msg.role"
          :content="msg.content"
          :agent-id="msg.agentId"
          :done="msg.done"
          :insight-chips="msg.insightChips"
          :tool-calls="msg.toolCalls"
          :timestamp="msg.timestamp"
          @chip-click="onInsightChipClick"
        />
      </template>
    </div>

    <button v-if="userScrolledUp && streaming" class="scroll-bottom" @click="scrollBottom(true)">回到底部</button>

    <AgentTraceBar
      v-if="handoffSteps.length || currentVerdict"
      :steps="handoffSteps"
      :verdict="currentVerdict"
      :verdict-reason="currentVerdictReason"
      @trace-click="onPhaseTraceClick"
    />

    <ChatTracePanel
      v-if="traceId"
      :trace-id="traceId"
      :phase-trace-label="phaseTraceLabel"
      :trace-data="traceData"
      :trace-loading="traceLoading"
      :trace-expanded="traceExpanded"
      @toggle="toggleTrace"
      @reset="resetToGlobalTrace"
      @inspect="emit('traceInspect', $event)"
    />

    <RunApprovalCard
      v-if="pendingApproval"
      :target-agent="pendingApproval.targetAgent"
      :risk="pendingApproval.risk"
      :reason="pendingApproval.reason"
      :resolving="resolvingApproval"
      @resolve="resolveApproval"
    />

    <ThoughtComposer
      v-model:input="input"
      v-model:streaming="streaming"
      @send="sendMessage"
      @abort="abortStream"
      @insert-command="insertCommand"
    />
  </div>
</template>

<style scoped>
.chat-studio {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.message-canvas {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 34px 0 22px;
}

.agent-activity,
.stale-warning {
  width: min(760px, calc(100% - 32px));
  margin: 12px auto 0;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--text-secondary);
  background: rgba(255,255,255,0.04);
  font-size: 12px;
  flex-shrink: 0;
}

.activity-dots { display: flex; gap: 4px; }
.activity-dots i { width: 7px; height: 7px; border-radius: 999px; animation: pulse-glow 1.4s ease-in-out infinite; }
.stale-warning { color: var(--color-warning); border-color: rgba(255,213,106,.20); background: rgba(255,213,106,.06); }
.stale-warning button { margin-left: auto; color: var(--color-warning); text-decoration: underline; text-underline-offset: 3px; }

.empty-hero {
  width: min(720px, calc(100% - 32px));
  margin: 0 auto;
  padding: min(14vh, 112px) 0 80px;
}
.empty-heading {
  display: flex;
  align-items: center;
  gap: 14px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--border-subtle);
}
.empty-mark {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  display: grid;
  place-items: center;
  border: 1px solid #31515c;
  border-radius: 7px;
  background: #17272d;
  color: #a8dce6;
  font-size: 12px;
  font-weight: 850;
}
.hero-kicker { margin: 0 0 4px; color: #82b8c4; font-size: 9px; font-weight: 800; text-transform: uppercase; }
.empty-hero h1 { margin: 0; color: var(--text-primary); font-size: 24px; line-height: 1.25; }
.hero-copy { margin: 16px 0 0; color: var(--text-secondary); font-size: 13px; line-height: 1.7; }
.hero-actions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 20px; }
.hero-actions button {
  min-height: 62px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  color: var(--text-secondary);
  text-align: left;
}
.hero-actions button:hover { background: var(--surface-hover); border-color: var(--border-strong); }
.hero-actions b { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 6px; font-size: 9px; }
.hero-actions b.knowledge { color: var(--agent-knowledge); background: rgba(121,174,255,.10); }
.hero-actions b.review { color: var(--agent-review); background: rgba(255,189,115,.10); }
.hero-actions b.brain { color: var(--agent-brain); background: rgba(196,154,255,.10); }
.hero-actions span { min-width: 0; display: grid; gap: 3px; }
.hero-actions strong { color: var(--text-primary); font-size: 11px; }
.hero-actions small { color: var(--text-tertiary); font-size: 10px; }
.task-hints { display: flex; align-items: center; gap: 6px; margin-top: 15px; color: var(--text-tertiary); font-size: 10px; }
.task-hints > span { margin-right: 4px; }
.task-hints button { padding: 5px 7px; border-radius: 5px; color: var(--text-secondary); font-size: 10px; }
.task-hints button:hover { background: var(--surface-hover); color: var(--text-primary); }

.scroll-bottom {
  position: absolute;
  left: 50%;
  bottom: 132px;
  transform: translateX(-50%);
  z-index: 5;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: rgba(20,22,31,.86);
  color: var(--text-secondary);
  padding: 8px 12px;
  font-size: 12px;
  box-shadow: 0 16px 50px rgba(0,0,0,.24);
}

@media (max-width: 740px) {
  .message-canvas { padding-top: 22px; }
  .hero-actions { grid-template-columns: 1fr; }
  .empty-hero h1 { font-size: 21px; }
}
</style>
