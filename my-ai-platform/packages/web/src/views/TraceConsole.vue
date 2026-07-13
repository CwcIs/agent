<script setup lang="ts">
import { ref, computed, onMounted } from "vue";

interface TraceSummary {
  trace_id: string;
  session_id: string;
  agents: string[];
  status: string;
  call_count: number;
  latency_ms: number;
  cost_usd: number;
  started_at: string;
  ended_at: string;
}

interface TraceDetail {
  trace_id: string;
  session_id: string;
  user_input: { content: string; created_at: string } | null;
  agents: Array<{
    agent_id: string;
    call_count: number;
    timeline: Array<{
      type: string;
      agent_id: string;
      timestamp: string;
      model?: string;
      input_tokens?: number;
      output_tokens?: number;
      cost_usd?: number;
      latency_ms?: number;
      status?: string;
    }>;
  }>;
  errors: Array<{
    id: string;
    error_type: string;
    error_msg: string;
    created_at: string;
  }>;
  summary: {
    total_tokens: number;
    total_cost_usd: number;
    total_latency_ms: number;
    call_count: number;
    agent_count: number;
    verdict: string;
    started_at: string;
    ended_at: string;
  };
}

const traces = ref<TraceSummary[]>([]);
const selectedTrace = ref<TraceDetail | null>(null);
const traceLoading = ref(false);
const listLoading = ref(true);
const filterAgent = ref("");
const filterStatus = ref("");
const filterText = ref("");

const filteredTraces = computed(() => {
  let list = traces.value;
  if (filterAgent.value) {
    list = list.filter(t => t.agents.some(a => a.includes(filterAgent.value)));
  }
  if (filterStatus.value) {
    list = list.filter(t => t.status === filterStatus.value);
  }
  if (filterText.value) {
    const q = filterText.value.toLowerCase();
    list = list.filter(t => t.trace_id.includes(q) || t.session_id.includes(q));
  }
  return list;
});

const uniqueAgents = computed(() => {
  const s = new Set<string>();
  traces.value.forEach(t => t.agents.forEach(a => s.add(a)));
  return [...s].sort();
});

onMounted(() => {
  refreshList();
});

async function refreshList() {
  listLoading.value = true;
  try {
    const resp = await fetch("/traces/recent?limit=50");
    if (resp.ok) {
      const data = await resp.json();
      traces.value = data.traces || [];
    }
  } catch { /* ignore */ }
  finally { listLoading.value = false; }
}

async function selectTrace(traceId: string) {
  traceLoading.value = true;
  selectedTrace.value = null;
  try {
    const resp = await fetch(`/traces/${traceId}`);
    if (resp.ok) {
      selectedTrace.value = await resp.json();
    }
  } catch { /* ignore */ }
  finally { traceLoading.value = false; }
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

function formatCost(usd: number): string {
  if (usd < 0.001) return "< $0.001";
  return `$${usd.toFixed(4)}`;
}

function formatTime(ts: string): string {
  if (!ts) return "";
  const d = new Date(ts + "Z");
  return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function verdictBadgeClass(verdict: string): string {
  switch (verdict) {
    case "natural_end": return "badge-ok";
    case "error":
    case "missing_handoff":
    case "loop_detected": return "badge-err";
    default: return "badge-neutral";
  }
}

function verdictLabel(verdict: string): string {
  switch (verdict) {
    case "natural_end": return "正常结束";
    case "error": return "错误";
    case "missing_handoff": return "未处理 handoff";
    case "loop_detected": return "检测到循环";
    default: return verdict;
  }
}
</script>

<template>
  <div class="flex flex-col h-full min-h-0" style="color: var(--text-primary)">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-2.5 border-b shrink-0" style="border-color: var(--border-subtle)">
      <div class="flex items-center gap-2">
        <span class="text-xs font-semibold uppercase tracking-wider" style="color: var(--text-muted)">Trace Console</span>
        <span class="text-[10px] px-1.5 py-0.5 rounded-full" style="background: rgba(255,255,255,0.05); color: var(--text-muted)">
          {{ traces.length }} traces
        </span>
      </div>
      <button
        class="text-[10px] px-2 py-1 rounded border hover:brightness-110 transition-all"
        style="color: var(--text-muted); border-color: var(--border-subtle)"
        @click="refreshList"
      >
        Refresh
      </button>
    </div>

    <div class="flex flex-1 min-h-0">
      <!-- Left: Trace List -->
      <div class="w-80 shrink-0 border-r flex flex-col min-h-0" style="border-color: var(--border-subtle)">
        <!-- Filters -->
        <div class="px-3 py-2 space-y-1.5 border-b shrink-0" style="border-color: var(--border-subtle)">
          <input
            v-model="filterText"
            type="text"
            placeholder="Search trace/session ID..."
            class="w-full text-[10px] px-2 py-1 rounded border bg-transparent outline-none focus:brightness-110"
            style="color: var(--text-primary); border-color: var(--border-subtle); caret-color: var(--agent-knowledge)"
          />
          <div class="flex gap-1">
            <select
              v-model="filterAgent"
              class="flex-1 text-[10px] px-1.5 py-0.5 rounded border bg-transparent outline-none"
              style="color: var(--text-muted); border-color: var(--border-subtle)"
            >
              <option value="">All Agents</option>
              <option v-for="a in uniqueAgents" :key="a" :value="a">{{ a }}</option>
            </select>
            <select
              v-model="filterStatus"
              class="flex-1 text-[10px] px-1.5 py-0.5 rounded border bg-transparent outline-none"
              style="color: var(--text-muted); border-color: var(--border-subtle)"
            >
              <option value="">All Status</option>
              <option value="ok">OK</option>
              <option value="error">Error</option>
            </select>
          </div>
        </div>

        <!-- Trace List -->
        <div class="flex-1 overflow-y-auto">
          <div v-if="listLoading" class="p-4 text-center">
            <span class="text-[11px]" style="color: var(--text-muted)">Loading traces…</span>
          </div>
          <div v-else-if="filteredTraces.length === 0" class="p-6 text-center">
            <span class="text-[11px]" style="color: var(--text-tertiary)">No traces found</span>
          </div>
          <button
            v-for="t in filteredTraces"
            :key="t.trace_id"
            class="w-full text-left px-3 py-2 border-b transition-all hover:brightness-110"
            :style="{
              borderColor: 'var(--border-subtle)',
              background: selectedTrace?.trace_id === t.trace_id ? 'rgba(124,156,255,0.06)' : 'transparent',
            }"
            @click="selectTrace(t.trace_id)"
          >
            <div class="flex items-center gap-1.5 mb-0.5">
              <span
                class="w-1.5 h-1.5 rounded-full shrink-0"
                :style="{ background: t.status === 'error' ? 'var(--agent-review)' : 'var(--agent-knowledge)' }"
              />
              <span class="text-[10px] font-mono truncate" style="color: var(--text-secondary)">{{ t.trace_id.slice(0, 8) }}…</span>
              <span
                class="text-[9px] px-1 rounded-full shrink-0 ml-auto"
                :class="t.status === 'error' ? 'badge-err' : 'badge-ok'"
              >{{ t.status === 'error' ? 'err' : 'ok' }}</span>
            </div>
            <div class="flex items-center gap-2 text-[9px]" style="color: var(--text-muted)">
              <span>{{ t.agents.join(", ") || "—" }}</span>
              <span>{{ t.call_count }} calls</span>
              <span>{{ formatLatency(t.latency_ms) }}</span>
              <span>{{ formatCost(t.cost_usd) }}</span>
            </div>
            <div class="text-[9px] mt-0.5" style="color: var(--text-tertiary)">{{ formatTime(t.started_at) }}</div>
          </button>
        </div>
      </div>

      <!-- Right: Trace Detail -->
      <div class="flex-1 flex flex-col min-h-0 min-w-0">
        <!-- Empty state -->
        <div v-if="!selectedTrace && !traceLoading" class="flex-1 flex items-center justify-center">
          <span class="text-xs" style="color: var(--text-tertiary)">Select a trace to view details</span>
        </div>

        <!-- Loading -->
        <div v-else-if="traceLoading" class="flex-1 flex items-center justify-center">
          <span class="text-xs" style="color: var(--text-muted)">Loading trace detail…</span>
        </div>

        <!-- Trace Detail -->
        <template v-else-if="selectedTrace">
          <!-- Summary Bar -->
          <div class="px-4 py-2.5 border-b shrink-0 flex items-center gap-3 flex-wrap" style="border-color: var(--border-subtle)">
            <span class="text-[10px] font-mono" style="color: var(--text-secondary)">{{ selectedTrace.trace_id }}</span>
            <span
              class="text-[9px] px-1.5 py-0.5 rounded-full"
              :class="verdictBadgeClass(selectedTrace.summary.verdict)"
            >{{ verdictLabel(selectedTrace.summary.verdict) }}</span>
            <span class="text-[9px]" style="color: var(--text-muted)">{{ selectedTrace.summary.agent_count }} agents</span>
            <span class="text-[9px]" style="color: var(--text-muted)">{{ selectedTrace.summary.call_count }} calls</span>
            <span class="text-[9px]" style="color: var(--text-muted)">{{ formatLatency(selectedTrace.summary.total_latency_ms) }}</span>
            <span class="text-[9px]" style="color: var(--text-muted)">{{ formatCost(selectedTrace.summary.total_cost_usd) }}</span>
            <span class="text-[9px]" style="color: var(--text-muted)">{{ selectedTrace.summary.total_tokens.toLocaleString() }} tokens</span>
          </div>

          <!-- Timeline Content -->
          <div class="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            <!-- User Input -->
            <div v-if="selectedTrace.user_input" class="mb-4">
              <div class="text-[9px] font-semibold uppercase tracking-wider mb-1" style="color: var(--text-tertiary)">User Input</div>
              <div class="text-xs rounded-lg px-3 py-2" style="background: rgba(255,255,255,0.02); color: var(--text-primary); white-space: pre-wrap;">
                {{ selectedTrace.user_input.content }}
              </div>
            </div>

            <!-- Agent Timelines -->
            <div v-for="agent in selectedTrace.agents" :key="agent.agent_id" class="mb-4">
              <div class="flex items-center gap-2 mb-2">
                <span class="text-[10px] font-semibold uppercase tracking-wider" style="color: var(--text-secondary)">{{ agent.agent_id }}</span>
                <span class="text-[9px] px-1 py-0.5 rounded-full" style="background: rgba(255,255,255,0.04); color: var(--text-muted)">{{ agent.call_count }} calls</span>
              </div>

              <!-- Timeline events -->
              <div class="relative pl-4 border-l" style="border-color: var(--border-subtle)">
                <div v-for="(event, ei) in agent.timeline" :key="ei" class="relative pb-2">
                  <!-- Dot -->
                  <div
                    class="absolute -left-[5px] w-2 h-2 rounded-full shrink-0"
                    :style="{
                      top: '3px',
                      background: event.type === 'agent_start' ? 'var(--agent-knowledge)' :
                                  event.type === 'agent_end' ? 'var(--text-muted)' :
                                  event.status === 'error' ? 'var(--agent-review)' : 'var(--text-tertiary)',
                      border: '2px solid var(--bg-app)',
                    }"
                  />

                  <!-- Event content -->
                  <div class="text-[10px]">
                    <span
                      v-if="event.type === 'agent_start'"
                      class="font-medium"
                      style="color: var(--agent-knowledge)"
                    >Agent Start: {{ event.agent_id }}</span>
                    <span
                      v-else-if="event.type === 'agent_end'"
                      style="color: var(--text-muted)"
                    >Agent End: {{ event.agent_id }}</span>
                    <div v-else-if="event.type === 'llm_call'" class="flex items-center gap-2 flex-wrap">
                      <span style="color: var(--text-secondary)">{{ event.model }}</span>
                      <span style="color: var(--text-muted)">{{ event.input_tokens }}+{{ event.output_tokens }} tok</span>
                      <span style="color: var(--text-muted)">{{ formatLatency(event.latency_ms || 0) }}</span>
                      <span style="color: var(--text-muted)">{{ formatCost(event.cost_usd || 0) }}</span>
                      <span
                        v-if="event.status === 'error'"
                        class="text-[9px] px-1 rounded-full badge-err"
                      >error</span>
                    </div>
                    <span class="text-[9px] ml-1" style="color: var(--text-tertiary)">{{ formatTime(event.timestamp) }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Errors -->
            <div v-if="selectedTrace.errors.length > 0">
              <div class="text-[9px] font-semibold uppercase tracking-wider mb-1" style="color: var(--agent-review)">Errors ({{ selectedTrace.errors.length }})</div>
              <div
                v-for="err in selectedTrace.errors"
                :key="err.id"
                class="text-[10px] rounded px-2.5 py-1.5 mb-1"
                style="background: rgba(239,68,68,0.06); color: var(--text-secondary); border: 1px solid rgba(239,68,68,0.1)"
              >
                <span class="font-medium" style="color: var(--agent-review)">{{ err.error_type }}</span>
                <span class="ml-2" style="color: var(--text-muted)">{{ err.error_msg }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.badge-ok {
  background: rgba(34,197,94,0.1);
  color: var(--agent-knowledge);
}
.badge-err {
  background: rgba(239,68,68,0.1);
  color: var(--agent-review);
}
.badge-neutral {
  background: rgba(255,255,255,0.05);
  color: var(--text-muted);
}
</style>
