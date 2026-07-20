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
        <div class="hero-orb">✦</div>
        <p class="hero-kicker">AI Thought Studio</p>
        <h1>{{ greeting }}，今天先捕捉哪一个想法？</h1>
        <p class="hero-copy">丢进一个碎片。我会帮你保存、连接旧笔记、挑战假设，或扩展成新的方向。</p>
        <div class="hero-actions">
          <button v-for="cmd in COMMANDS" :key="cmd.trigger" :style="{ borderColor: cmd.border, color: cmd.color, background: cmd.bg }" @click="insertCommand(cmd.trigger)">
            {{ cmd.trigger }} · {{ cmd.desc }}
          </button>
        </div>
        <div class="hero-grid">
          <div>
            <strong>Capture</strong>
            <span>把碎片想法先收进来</span>
          </div>
          <div>
            <strong>Review</strong>
            <span>找出假设、漏洞和风险</span>
          </div>
          <div>
            <strong>Brain</strong>
            <span>联想相邻概念与可能性</span>
          </div>
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
  min-height: 100%;
  width: min(820px, calc(100% - 32px));
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: 48px 0 130px;
}

.hero-orb {
  width: 58px;
  height: 58px;
  border-radius: 22px;
  display: grid;
  place-items: center;
  color: white;
  background: linear-gradient(135deg, var(--brand), var(--brand-2));
  box-shadow: 0 24px 70px rgba(154,134,255,.28);
  margin-bottom: 18px;
}
.hero-kicker { margin: 0 0 8px; color: var(--brand-2); font-size: 11px; font-weight: 800; letter-spacing: .16em; text-transform: uppercase; }
.empty-hero h1 { margin: 0; max-width: 720px; color: var(--text-primary); font-size: clamp(30px, 5vw, 56px); line-height: 1.04; letter-spacing: -0.065em; }
.hero-copy { max-width: 560px; margin: 18px auto 0; color: var(--text-secondary); font-size: 15px; line-height: 1.75; }
.hero-actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin-top: 26px; }
.hero-actions button { border: 1px solid; border-radius: 999px; padding: 9px 13px; font-size: 12px; transition: 160ms ease; }
.hero-actions button:hover { transform: translateY(-1px); filter: brightness(1.12); }
.hero-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; width: min(680px, 100%); margin-top: 30px; }
.hero-grid div { border: 1px solid var(--border-subtle); border-radius: 18px; background: rgba(255,255,255,.035); padding: 16px; text-align: left; }
.hero-grid strong { display: block; color: var(--text-primary); font-size: 13px; margin-bottom: 5px; }
.hero-grid span { color: var(--text-tertiary); font-size: 12px; line-height: 1.5; }

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
  .hero-grid { grid-template-columns: 1fr; }
  .empty-hero h1 { font-size: 34px; }
}
</style>
