<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  eventLabel,
  eventSummary,
  formatCost,
  formatLatency,
  formatTraceTime,
  trustLabel,
} from "../trace/model";
import type { TraceDetail, TraceEvent, TraceSummary, TrustStatus } from "../trace/model";

type DetailTab = "timeline" | "evidence" | "raw";

const traces = ref<TraceSummary[]>([]);
const selectedTrace = ref<TraceDetail | null>(null);
const traceLoading = ref(false);
const listLoading = ref(true);
const loadError = ref("");
const filterAgent = ref("");
const filterStatus = ref("");
const filterText = ref("");
const activeTab = ref<DetailTab>("timeline");
const detailTabs: DetailTab[] = ["timeline", "evidence", "raw"];

const filteredTraces = computed(() => {
  let list = traces.value;
  if (filterAgent.value) {
    list = list.filter((trace) => trace.agents.includes(filterAgent.value));
  }
  if (filterStatus.value) {
    list = list.filter((trace) => trace.status === filterStatus.value);
  }
  if (filterText.value) {
    const query = filterText.value.toLowerCase();
    list = list.filter(
      (trace) =>
        trace.trace_id.toLowerCase().includes(query) ||
        trace.session_id.toLowerCase().includes(query),
    );
  }
  return list;
});

const uniqueAgents = computed(() => {
  const agents = new Set<string>();
  traces.value.forEach((trace) => trace.agents.forEach((agent) => agents.add(agent)));
  return [...agents].sort();
});

const trustCounts = computed(() => {
  const counts: Record<TrustStatus, number> = {
    verified: 0,
    degraded: 0,
    partial: 0,
    compromised: 0,
  };
  traces.value.forEach((trace) => {
    counts[trace.status] = (counts[trace.status] || 0) + 1;
  });
  return counts;
});

function trustClass(status: TrustStatus): string {
  return {
    verified: "trust-ok",
    degraded: "trust-warn",
    partial: "trust-partial",
    compromised: "trust-bad",
  }[status];
}

function eventClass(event: TraceEvent): string {
  if (event.status === "error" || event.event_type === "error") return "event-bad";
  if (event.status === "warning" || event.event_type === "warning") return "event-warn";
  if (["retrieval_completed", "citation_verified", "verdict"].includes(event.event_type)) return "event-accent";
  return "event-neutral";
}

function prettyPayload(event: TraceEvent): string {
  return JSON.stringify(event.payload || {}, null, 2);
}

async function refreshList() {
  listLoading.value = true;
  loadError.value = "";
  try {
    const response = await fetch("/traces/recent?limit=100");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    traces.value = data.traces || [];
  } catch (error) {
    loadError.value = `无法加载 Trace 列表：${String(error)}`;
  } finally {
    listLoading.value = false;
  }
}

async function selectTrace(traceId: string) {
  traceLoading.value = true;
  loadError.value = "";
  activeTab.value = "timeline";
  try {
    const response = await fetch(`/traces/${traceId}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    selectedTrace.value = await response.json();
  } catch (error) {
    selectedTrace.value = null;
    loadError.value = `无法加载 Trace 详情：${String(error)}`;
  } finally {
    traceLoading.value = false;
  }
}

onMounted(refreshList);
</script>

<template>
  <div class="flex h-full min-h-0 flex-col" style="color: var(--text-primary)">
    <header class="flex shrink-0 items-center gap-3 border-b px-4 py-2.5" style="border-color: var(--border-subtle)">
      <div>
        <h1 class="text-xs font-semibold">Trace Console</h1>
        <p class="text-[10px]" style="color: var(--text-muted)">全链路证据、完整性与成本审计</p>
      </div>
      <div class="ml-3 flex items-center gap-2 text-[10px]" style="color: var(--text-muted)">
        <span>{{ traces.length }} 条</span>
        <span class="trust-ok px-1.5 py-0.5">{{ trustCounts.verified }} 已校验</span>
        <span v-if="trustCounts.compromised" class="trust-bad px-1.5 py-0.5">
          {{ trustCounts.compromised }} 校验失败
        </span>
      </div>
      <button
        class="ml-auto border px-2 py-1 text-[10px] transition-opacity hover:opacity-80"
        style="border-color: var(--border-subtle); color: var(--text-secondary)"
        title="刷新 Trace"
        @click="refreshList"
      >
        刷新
      </button>
    </header>

    <div v-if="loadError" class="shrink-0 border-b px-4 py-2 text-[11px] event-bad">
      {{ loadError }}
    </div>

    <div class="flex min-h-0 flex-1 flex-col lg:flex-row">
      <aside class="flex max-h-[42%] w-full shrink-0 flex-col border-b lg:max-h-none lg:w-80 lg:border-b-0 lg:border-r" style="border-color: var(--border-subtle)">
        <div class="grid shrink-0 grid-cols-2 gap-1.5 border-b p-3" style="border-color: var(--border-subtle)">
          <input
            v-model="filterText"
            class="col-span-2 border bg-transparent px-2 py-1.5 text-[10px] outline-none"
            style="border-color: var(--border-subtle)"
            placeholder="搜索 trace / session ID"
          />
          <select v-model="filterAgent" class="border bg-transparent px-1.5 py-1 text-[10px]" style="border-color: var(--border-subtle)">
            <option value="">全部 Agent</option>
            <option v-for="agent in uniqueAgents" :key="agent" :value="agent">{{ agent }}</option>
          </select>
          <select v-model="filterStatus" class="border bg-transparent px-1.5 py-1 text-[10px]" style="border-color: var(--border-subtle)">
            <option value="">全部可信状态</option>
            <option value="verified">已校验</option>
            <option value="degraded">有错误</option>
            <option value="partial">证据不完整</option>
            <option value="compromised">校验失败</option>
          </select>
        </div>

        <div class="flex-1 overflow-y-auto">
          <div v-if="listLoading" class="p-5 text-center text-[11px]" style="color: var(--text-muted)">正在加载…</div>
          <div v-else-if="!filteredTraces.length" class="p-5 text-center text-[11px]" style="color: var(--text-muted)">没有匹配的 Trace</div>
          <button
            v-for="trace in filteredTraces"
            :key="trace.trace_id"
            class="w-full border-b px-3 py-2.5 text-left transition-colors"
            :style="{
              borderColor: 'var(--border-subtle)',
              background: selectedTrace?.trace_id === trace.trace_id ? 'rgba(124,156,255,0.06)' : 'transparent',
            }"
            @click="selectTrace(trace.trace_id)"
          >
            <div class="flex items-center gap-2">
              <span class="h-2 w-2 shrink-0 rounded-full" :class="trustClass(trace.status)" />
              <code class="truncate text-[10px]" style="color: var(--text-secondary)">{{ trace.trace_id.slice(0, 12) }}</code>
              <span class="ml-auto px-1.5 py-0.5 text-[9px]" :class="trustClass(trace.status)">
                {{ trace.trust_score }}
              </span>
            </div>
            <div class="mt-1 flex gap-2 text-[9px]" style="color: var(--text-muted)">
              <span>{{ trace.agents.join(" → ") || "无 Agent" }}</span>
              <span>{{ trace.event_count }} events</span>
            </div>
            <div class="mt-1 flex gap-2 text-[9px]" style="color: var(--text-tertiary)">
              <span>{{ trace.call_count }} LLM</span>
              <span>{{ trace.tool_count }} tools</span>
              <span>{{ formatCost(trace.cost_usd) }}</span>
              <span class="ml-auto">{{ formatTraceTime(trace.started_at) }}</span>
            </div>
          </button>
        </div>
      </aside>

      <main class="flex min-h-0 min-w-0 flex-1 flex-col">
        <div v-if="!selectedTrace && !traceLoading" class="flex flex-1 items-center justify-center text-xs" style="color: var(--text-tertiary)">
          选择一条 Trace 查看链路证据
        </div>
        <div v-else-if="traceLoading" class="flex flex-1 items-center justify-center text-xs" style="color: var(--text-muted)">
          正在校验事件账本…
        </div>

        <template v-else-if="selectedTrace">
          <section class="shrink-0 border-b" style="border-color: var(--border-subtle)">
            <div class="flex flex-wrap items-center gap-3 px-4 py-2">
              <code class="text-[10px]" style="color: var(--text-secondary)">{{ selectedTrace.trace_id }}</code>
              <span class="px-1.5 py-0.5 text-[9px]" :class="trustClass(selectedTrace.trust.status)">
                {{ trustLabel(selectedTrace.trust.status) }} · {{ selectedTrace.trust.score }}
              </span>
              <span class="text-[9px]" style="color: var(--text-muted)">{{ selectedTrace.scope }}</span>
              <span class="ml-auto text-[9px]" style="color: var(--text-muted)">
                {{ selectedTrace.summary.verdict }}
              </span>
            </div>

            <div class="grid grid-cols-2 border-t sm:grid-cols-4 lg:grid-cols-7" style="border-color: var(--border-subtle)">
              <div class="metric"><span>事件</span><strong>{{ selectedTrace.events.length }}</strong></div>
              <div class="metric"><span>Agent</span><strong>{{ selectedTrace.summary.agent_count }}</strong></div>
              <div class="metric"><span>LLM</span><strong>{{ selectedTrace.summary.call_count }}</strong></div>
              <div class="metric"><span>工具</span><strong>{{ selectedTrace.summary.tool_count }}</strong></div>
              <div class="metric"><span>检索</span><strong>{{ selectedTrace.summary.retrieval_count }}</strong></div>
              <div class="metric"><span>Token</span><strong>{{ selectedTrace.summary.total_tokens.toLocaleString() }}</strong></div>
              <div class="metric"><span>成本</span><strong>{{ formatCost(selectedTrace.summary.total_cost_usd) }}</strong></div>
            </div>

            <div class="grid grid-cols-1 border-t text-[10px] sm:grid-cols-2 lg:grid-cols-6" style="border-color: var(--border-subtle)">
              <div class="audit-line">
                <span>账本哈希</span>
                <strong :class="selectedTrace.trust.ledger.valid ? 'text-ok' : 'text-bad'">
                  {{ selectedTrace.trust.ledger.valid ? "连续" : "失败" }}
                </strong>
              </div>
              <div class="audit-line">
                <span>必要事件</span>
                <strong :class="selectedTrace.trust.missing_required_events.length ? 'text-warn' : 'text-ok'">
                  {{ selectedTrace.trust.missing_required_events.length ? `缺 ${selectedTrace.trust.missing_required_events.length}` : "完整" }}
                </strong>
              </div>
              <div class="audit-line">
                <span>未闭合工具</span>
                <strong :class="selectedTrace.trust.open_tool_calls.length ? 'text-bad' : 'text-ok'">
                  {{ selectedTrace.trust.open_tool_calls.length }}
                </strong>
              </div>
              <div class="audit-line">
                <span>可验证引用</span>
                <strong>{{ selectedTrace.trust.verified_citation_count }} / {{ selectedTrace.trust.retrieved_note_count }}</strong>
              </div>
              <div class="audit-line">
                <span>警告</span>
                <strong :class="selectedTrace.trust.warning_count ? 'text-warn' : ''">{{ selectedTrace.trust.warning_count }}</strong>
              </div>
              <div class="audit-line">
                <span>错误</span>
                <strong :class="selectedTrace.trust.error_count ? 'text-bad' : 'text-ok'">{{ selectedTrace.trust.error_count }}</strong>
              </div>
            </div>
          </section>

          <nav class="flex shrink-0 gap-1 border-b px-4 py-1.5" style="border-color: var(--border-subtle)">
            <button
              v-for="tab in detailTabs"
              :key="tab"
              class="px-2 py-1 text-[10px]"
              :style="{
                color: activeTab === tab ? 'var(--text-primary)' : 'var(--text-muted)',
                background: activeTab === tab ? 'rgba(255,255,255,0.06)' : 'transparent',
              }"
              @click="activeTab = tab"
            >
              {{ tab === "timeline" ? "事件时间线" : tab === "evidence" ? "证据与诊断" : "原始事件" }}
            </button>
          </nav>

          <div class="flex-1 overflow-y-auto">
            <section v-if="activeTab === 'timeline'">
              <div v-if="selectedTrace.user_input" class="border-b px-4 py-3" style="border-color: var(--border-subtle)">
                <div class="mb-1 flex items-center gap-2 text-[9px]" style="color: var(--text-muted)">
                  <span>用户输入</span>
                  <code>SHA {{ selectedTrace.user_input.sha256?.slice(0, 12) }}</code>
                  <span v-if="selectedTrace.user_input.truncated">预览已截断</span>
                </div>
                <p class="whitespace-pre-wrap text-xs">{{ selectedTrace.user_input.content }}</p>
              </div>

              <div
                v-for="event in selectedTrace.events"
                :key="event.id"
                class="grid grid-cols-[42px_10px_minmax(0,1fr)] gap-3 border-b px-4 py-2.5"
                style="border-color: var(--border-subtle)"
              >
                <span class="text-right font-mono text-[9px]" style="color: var(--text-tertiary)">#{{ event.sequence }}</span>
                <span class="mt-1 h-2 w-2 rounded-full" :class="eventClass(event)" />
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <strong class="text-[10px]">{{ eventLabel(event.event_type) }}</strong>
                    <span v-if="event.agent_id" class="text-[9px]" style="color: var(--text-muted)">{{ event.agent_id }}</span>
                    <code v-if="event.phase_trace_id" class="text-[9px]" style="color: var(--text-tertiary)">{{ event.phase_trace_id.slice(0, 8) }}</code>
                    <span class="ml-auto text-[9px]" style="color: var(--text-tertiary)">{{ formatTraceTime(event.created_at) }}</span>
                  </div>
                  <p class="mt-0.5 truncate text-[10px]" style="color: var(--text-secondary)">{{ eventSummary(event) }}</p>
                </div>
              </div>
            </section>

            <section v-else-if="activeTab === 'evidence'" class="divide-y" style="border-color: var(--border-subtle)">
              <div class="px-4 py-3">
                <h2 class="text-[10px] font-semibold">可信声明</h2>
                <p class="mt-1 text-[10px]" style="color: var(--text-muted)">{{ selectedTrace.trust.claim }}</p>
                <code class="mt-1 block break-all text-[9px]" style="color: var(--text-tertiary)">
                  head {{ selectedTrace.trust.ledger.head_hash || "unavailable" }}
                </code>
              </div>

              <div v-if="selectedTrace.trust.missing_required_events.length" class="px-4 py-3">
                <h2 class="text-[10px] font-semibold text-warn">缺失必要事件</h2>
                <p class="mt-1 text-[10px]" style="color: var(--text-muted)">
                  {{ selectedTrace.trust.missing_required_events.join(", ") }}
                </p>
              </div>

              <div v-if="selectedTrace.trust.structural_issues.length" class="px-4 py-3">
                <h2 class="text-[10px] font-semibold text-bad">链路结构异常</h2>
                <p class="mt-1 text-[10px]" style="color: var(--text-muted)">
                  {{ selectedTrace.trust.structural_issues.join(", ") }}
                </p>
              </div>

              <div v-if="selectedTrace.trust.open_tool_calls.length" class="px-4 py-3">
                <h2 class="text-[10px] font-semibold text-bad">未闭合工具调用</h2>
                <div v-for="tool in selectedTrace.trust.open_tool_calls" :key="tool.tool_call_id" class="mt-1 text-[10px]">
                  {{ tool.agent_id }} · {{ tool.name }} · <code>{{ tool.tool_call_id }}</code>
                </div>
              </div>

              <div class="px-4 py-3">
                <h2 class="text-[10px] font-semibold">检索证据（{{ selectedTrace.evidence.retrievals.length }}）</h2>
                <div v-if="!selectedTrace.evidence.retrievals.length" class="mt-2 text-[10px]" style="color: var(--text-muted)">本链路没有检索事件</div>
                <div v-for="retrieval in selectedTrace.evidence.retrievals" :key="retrieval.id" class="mt-2 border-t pt-2" style="border-color: var(--border-subtle)">
                  <div class="flex gap-2 text-[10px]">
                    <span>{{ retrieval.agent_id }}</span>
                    <span style="color: var(--text-muted)">{{ eventSummary(retrieval) }}</span>
                    <code class="ml-auto text-[9px]">query {{ String(retrieval.payload.query_sha256 || "").slice(0, 10) }}</code>
                  </div>
                  <div
                    v-for="note in retrieval.payload.selected || []"
                    :key="note.note_id"
                    class="mt-1 grid grid-cols-[minmax(0,1fr)_repeat(3,52px)] gap-2 text-[9px]"
                    style="color: var(--text-muted)"
                  >
                    <span class="truncate">{{ note.title || note.note_id }}</span>
                    <span>final {{ note.ranker?.final_score ?? "—" }}</span>
                    <span>sem {{ note.ranker?.semantic_score ?? "—" }}</span>
                    <span>graph {{ note.ranker?.graph_score ?? "—" }}</span>
                  </div>
                </div>
              </div>

              <div class="px-4 py-3">
                <h2 class="text-[10px] font-semibold">可验证引用（{{ selectedTrace.evidence.citations.length }}）</h2>
                <p v-if="!selectedTrace.evidence.citations.length" class="mt-1 text-[10px]" style="color: var(--text-muted)">
                  没有检测到最终输出中的精确 note_id，不能声称引用已验证。
                </p>
                <div v-for="citation in selectedTrace.evidence.citations" :key="`${citation.sequence}-${citation.note_id}`" class="mt-1 text-[10px]">
                  {{ citation.agent_id }} · <code>{{ citation.note_id }}</code> · {{ citation.verification }}
                </div>
              </div>
            </section>

            <section v-else>
              <details v-for="event in selectedTrace.events" :key="event.id" class="border-b px-4 py-2" style="border-color: var(--border-subtle)">
                <summary class="cursor-pointer text-[10px]">
                  #{{ event.sequence }} {{ event.event_type }} · {{ event.agent_id || "system" }}
                </summary>
                <pre class="mt-2 overflow-x-auto whitespace-pre-wrap break-all text-[9px]" style="color: var(--text-muted)">{{ prettyPayload(event) }}</pre>
                <div class="mt-2 break-all font-mono text-[8px]" style="color: var(--text-tertiary)">
                  prev {{ event.prev_hash || "—" }}<br />
                  hash {{ event.event_hash || "—" }}
                </div>
              </details>
            </section>
          </div>
        </template>
      </main>
    </div>
  </div>
</template>

<style scoped>
.metric {
  min-width: 0;
  border-right: 1px solid var(--border-subtle);
  padding: 8px 12px;
}
.metric span {
  display: block;
  color: var(--text-muted);
  font-size: 9px;
}
.metric strong {
  display: block;
  margin-top: 2px;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 11px;
  text-overflow: ellipsis;
}
.audit-line {
  display: flex;
  justify-content: space-between;
  border-right: 1px solid var(--border-subtle);
  padding: 7px 12px;
  color: var(--text-muted);
}
.audit-line strong { color: var(--text-secondary); }
.trust-ok, .event-accent {
  background: rgba(34,197,94,0.12);
  color: #66d28b;
}
.trust-warn, .event-warn {
  background: rgba(245,158,11,0.12);
  color: #f5b942;
}
.trust-partial {
  background: rgba(148,163,184,0.12);
  color: #aab4c3;
}
.trust-bad, .event-bad {
  background: rgba(239,68,68,0.12);
  color: #f27b7b;
}
.event-neutral {
  background: rgba(148,163,184,0.22);
}
.text-ok { color: #66d28b !important; }
.text-warn { color: #f5b942 !important; }
.text-bad { color: #f27b7b !important; }
</style>
