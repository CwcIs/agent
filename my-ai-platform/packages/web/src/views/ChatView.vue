<script setup lang="ts">
import { ref, nextTick, onUnmounted, computed } from "vue";
import AgentDivider from "../components/AgentDivider.vue";
import AgentTraceBar from "../components/AgentTraceBar.vue";
import ChatTracePanel from "../components/ChatTracePanel.vue";
import ThoughtBlock from "../components/ThoughtBlock.vue";
import type { InsightChipData } from "../components/InsightChip.vue";
import ThoughtComposer from "../components/ThoughtComposer.vue";
import {
  AGENT_VERB,
  COMMANDS,
  TAG_LABEL,
  buildChipsFromTool,
  getOrCreateSessionId,
  parseTag,
} from "../chat/model";
import type { HandoffStep, Message } from "../chat/model";
import { readSSEStream } from "../chat/sse";
import { useChatTrace } from "../composables/useChatTrace";

const sessionId = getOrCreateSessionId();

const emit = defineEmits<{ noteSaved: [] }>();
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
const activeTag = computed(() => parseTag(input.value));
const messagesEl = ref<HTMLElement | null>(null);

let abortController: AbortController | null = null;

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

// 鈹€鈹€ 绌虹姸鎬侀棶鍊?鈹€鈹€
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
    <!-- 骞惰鎵ц鐘舵€佹í骞?-->
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
        <span style="color: var(--text-muted)">{{ runningAgents.join("  路  ") }}</span>
      </div>
    </div>

    <!-- Stale 鐪嬮棬鐙?-->
    <div
      v-if="showStaleWarning && streaming"
      class="px-4 py-2 border-b shrink-0"
      style="background: rgba(255,209,102,0.06); border-color: rgba(255,209,102,0.1)"
    >
      <div class="flex items-center gap-2 text-[11px]" style="color: #FFD166">
        <svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.94-1.24 2.502-2.784a10.5 10.5 0 00-5.864-6.535M12 3.75A10.5 10.5 0 0117.364 18H6.636A10.5 10.5 0 0112 3.75z" />
        </svg>
        <span>连接可能已断开，超过 {{ STALE_TIMEOUT_MS / 1000 }} 秒没有收到响应</span>
        <button class="ml-auto underline underline-offset-2 hover:opacity-80" style="color: #FFD166" @click="abortStream">停止并重试</button>
      </div>
    </div>

    <!-- 娑堟伅鍒楄〃 -->
    <div ref="messagesEl" class="flex-1 overflow-y-auto px-4 py-3 space-y-4" @scroll="onMessagesScroll">
      <!-- 绌虹姸鎬?-->
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

      <!-- 娑堟伅娓叉煋 -->
      <template v-for="(msg, i) in messages" :key="i">
        <!-- Agent 鍒囨崲鍒嗛殧鏉?-->
        <AgentDivider
          v-if="msg.isSwitchBanner"
          :agent-id="msg.agentId || 'knowledge'"
          :label="TAG_LABEL[msg.agentId || ''] || msg.agentId || 'Knowledge'"
          :verb="AGENT_VERB[msg.agentId || ''] || '姝ｅ湪澶勭悊'"
          :verdict="i === messages.length - 1 ? currentVerdict : null"
          :verdict-warning="i === messages.length - 1 ? currentVerdictReason : null"
        />

        <!-- 鏅€氭秷鎭紙鏂囨。鍧楅鏍硷級 -->
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

    <!-- 鍥炲埌搴曢儴娴挳 -->
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
        鍥炲埌搴曢儴
      </button>
    </div>

    <!-- Agent Trace Bar (handoff chain) -->
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
    />
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

