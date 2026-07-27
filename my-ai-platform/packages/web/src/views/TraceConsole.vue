<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  agentMeta,
  buildTraceSpans,
  eventLabel,
  eventSummary,
  eventTone,
  formatCost,
  formatLatency,
  formatTraceTime,
  importantEvents,
  trustLabel,
  verdictDescription,
  verdictLabel,
} from "../trace/model";
import type { TraceDetail, TraceEvent, TraceSpan, TraceSummary, TrustStatus } from "../trace/model";

type DetailTab = "overview" | "timeline" | "evidence" | "raw";
type TimelineFilter = "all" | "model" | "tool" | "handoff" | "issue";

const props = defineProps<{ initialTraceId?: string | null }>();
const emit = defineEmits<{ close: [] }>();
const traces = ref<TraceSummary[]>([]);
const selectedTrace = ref<TraceDetail | null>(null);
const traceLoading = ref(false);
const listLoading = ref(true);
const loadError = ref("");
const filterAgent = ref("");
const filterStatus = ref("");
const filterText = ref("");
const activeTab = ref<DetailTab>("overview");
const selectedSpan = ref<TraceSpan | null>(null);
const timelineFilter = ref<TimelineFilter>("all");
const timelineSearch = ref("");
const actionNotice = ref("");
let liveRefreshTimer: ReturnType<typeof setInterval> | null = null;

const detailTabs: Array<{ id: DetailTab; label: string }> = [
  { id: "overview", label: "执行摘要" },
  { id: "timeline", label: "完整时间线" },
  { id: "evidence", label: "证据与校验" },
  { id: "raw", label: "原始事件" },
];
const timelineFilters: Array<{ id: TimelineFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "model", label: "模型" },
  { id: "tool", label: "工具/检索" },
  { id: "handoff", label: "Agent 接力" },
  { id: "issue", label: "异常" },
];

const filteredTraces = computed(() => {
  let list = traces.value;
  if (filterAgent.value) list = list.filter((trace) => trace.agents.includes(filterAgent.value));
  if (filterStatus.value) list = list.filter((trace) => trace.status === filterStatus.value);
  if (filterText.value) {
    const query = filterText.value.toLowerCase();
    list = list.filter((trace) =>
      trace.trace_id.toLowerCase().includes(query) ||
      trace.session_id.toLowerCase().includes(query) ||
      trace.input_preview?.toLowerCase().includes(query) ||
      trace.agents.some((agent) => agent.toLowerCase().includes(query)),
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
  traces.value.forEach((trace) => { counts[trace.status] += 1; });
  return counts;
});

const selectedTitle = computed(() => {
  const content = selectedTrace.value?.user_input?.content?.trim();
  if (!content) return "一次 Agent 执行";
  return content.length > 72 ? `${content.slice(0, 72)}…` : content;
});

const keyTimeline = computed(() =>
  selectedTrace.value ? importantEvents(selectedTrace.value.events) : [],
);

const llmEvents = computed(() =>
  selectedTrace.value?.events.filter((event) => event.event_type === "llm_call") || [],
);

const flowSpans = computed(() => selectedTrace.value ? buildTraceSpans(selectedTrace.value.events) : []);

const flowStart = computed(() => {
  return flowSpans.value[0]?.startMs || 0;
});

const flowDuration = computed(() => {
  if (!flowSpans.value.length) return 1;
  const end = Math.max(...flowSpans.value.map((span) => span.startMs + span.durationMs));
  return Math.max(1, end - flowStart.value);
});

const slowestSpan = computed(() => [...flowSpans.value].sort((a, b) => b.durationMs - a.durationMs)[0] || null);

const issueCount = computed(() => selectedTrace.value
  ? selectedTrace.value.trust.error_count + selectedTrace.value.trust.warning_count
    + selectedTrace.value.trust.structural_issues.length
    + selectedTrace.value.trust.missing_required_events.length
  : 0,
);

const filteredTimeline = computed(() => {
  if (!selectedTrace.value) return [];
  const groups: Record<string, string[]> = {
    model: ["llm_call"],
    tool: ["tool_start", "tool_end", "retrieval_completed"],
    handoff: ["handoff_proposed", "policy_decision", "handoff", "agent_start", "agent_end"],
    issue: ["warning", "error"],
  };
  const allowed = timelineFilter.value === "all" ? null : groups[timelineFilter.value];
  const query = timelineSearch.value.trim().toLowerCase();
  return selectedTrace.value.events.filter((event) => {
    if (allowed && !allowed.includes(event.event_type) && !(timelineFilter.value === "issue" && event.status === "error")) return false;
    if (!query) return true;
    return [
      event.event_type,
      event.name,
      event.agent_id,
      eventSummary(event),
      JSON.stringify(event.payload || {}),
    ].some((value) => String(value).toLowerCase().includes(query));
  });
});

function spanOffset(span: TraceSpan): number {
  return Math.max(0, Math.min(94, ((span.startMs - flowStart.value) / flowDuration.value) * 100));
}

function spanWidth(span: TraceSpan): number {
  return Math.max(1.8, Math.min(100 - spanOffset(span), (span.durationMs / flowDuration.value) * 100));
}

function selectSpan(span: TraceSpan) {
  selectedSpan.value = span;
}

function trustClass(status: TrustStatus): string {
  return `trust-${status}`;
}

function prettyPayload(event: TraceEvent): string {
  return JSON.stringify(event.payload || {}, null, 2);
}

function phaseLabel(trace: TraceDetail): string {
  if (trace.scope === "phase") return "单 Agent 阶段";
  if (trace.scope === "legacy_phase") return "历史调用记录";
  return "完整执行链路";
}

function selectedNotes(event: TraceEvent): Array<Record<string, any>> {
  return Array.isArray(event.payload?.selected) ? event.payload.selected : [];
}

async function refreshList() {
  listLoading.value = true;
  loadError.value = "";
  try {
    const response = await fetch("/traces/recent?limit=100");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    traces.value = data.traces || [];
    if (!selectedTrace.value && traces.value.length) {
      const target = props.initialTraceId
        && traces.value.some((trace) => trace.trace_id === props.initialTraceId)
        ? props.initialTraceId
        : traces.value[0].trace_id;
      await selectTrace(target);
    }
  } catch (error) {
    loadError.value = `无法加载 Trace 列表：${String(error)}`;
  } finally {
    listLoading.value = false;
  }
}

async function selectTrace(traceId: string) {
  traceLoading.value = true;
  loadError.value = "";
  activeTab.value = "overview";
  selectedSpan.value = null;
  try {
    const response = await fetch(`/traces/${traceId}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    selectedTrace.value = await response.json();
    const url = new URL(window.location.href);
    url.searchParams.set("trace", "1");
    url.searchParams.set("traceId", selectedTrace.value!.trace_id);
    window.history.replaceState({}, "", url);
  } catch (error) {
    selectedTrace.value = null;
    loadError.value = `无法加载 Trace 详情：${String(error)}`;
  } finally {
    traceLoading.value = false;
  }
}

async function refreshSelectedTrace() {
  if (!selectedTrace.value || selectedTrace.value.summary.verdict !== "incomplete") return;
  try {
    const response = await fetch(`/traces/${selectedTrace.value.requested_trace_id}`);
    if (response.ok) selectedTrace.value = await response.json();
  } catch {
    // Live refresh is supplementary and should not interrupt inspection.
  }
}

async function copyTraceId() {
  if (!selectedTrace.value) return;
  await navigator.clipboard.writeText(selectedTrace.value.trace_id);
  actionNotice.value = "Trace ID 已复制";
  window.setTimeout(() => { actionNotice.value = ""; }, 1600);
}

function exportTrace() {
  if (!selectedTrace.value) return;
  const blob = new Blob([JSON.stringify(selectedTrace.value, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `trace-${selectedTrace.value.trace_id.slice(0, 8)}.json`;
  link.click();
  URL.revokeObjectURL(url);
  actionNotice.value = "Trace JSON 已导出";
  window.setTimeout(() => { actionNotice.value = ""; }, 1600);
}

function onConsoleKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement;
  if (["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName)) return;
  if (!["ArrowDown", "ArrowUp", "j", "k"].includes(event.key)) return;
  event.preventDefault();
  const current = filteredTraces.value.findIndex((trace) => trace.trace_id === selectedTrace.value?.trace_id);
  const delta = event.key === "ArrowDown" || event.key === "j" ? 1 : -1;
  const next = Math.max(0, Math.min(filteredTraces.value.length - 1, current + delta));
  const trace = filteredTraces.value[next];
  if (trace) selectTrace(trace.trace_id);
}

onMounted(() => {
  refreshList();
  document.addEventListener("keydown", onConsoleKeydown);
  liveRefreshTimer = setInterval(refreshSelectedTrace, 3000);
});

onUnmounted(() => {
  document.removeEventListener("keydown", onConsoleKeydown);
  if (liveRefreshTimer) clearInterval(liveRefreshTimer);
});
</script>

<template>
  <div class="trace-console">
    <header class="console-header">
      <div class="header-brand">
        <div class="brand-mark"><span /><span /><span /></div>
        <div>
          <div class="eyebrow">EXECUTION OBSERVATORY</div>
          <h1>Trace 看板</h1>
        </div>
      </div>

      <div class="header-health">
        <div class="health-dot" :class="{ live: selectedTrace?.summary.verdict === 'incomplete' }" />
        <span>{{ traces.length }} 次执行</span>
        <span class="header-divider" />
        <span v-if="selectedTrace?.summary.verdict === 'incomplete'">正在追踪执行</span>
        <span v-else>{{ trustCounts.verified }} 条可信链路</span>
      </div>

      <div class="header-actions">
        <button class="icon-button" title="刷新 Trace" @click="refreshList">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M20 6v5h-5M4 18v-5h5M6.1 9a7 7 0 0 1 11.5-2.6L20 11M4 13l2.4 4.6A7 7 0 0 0 18 15" /></svg>
        </button>
        <button class="close-button" @click="emit('close')">关闭 <kbd>Esc</kbd></button>
      </div>
    </header>

    <div v-if="loadError" class="error-banner">
      <span>!</span>{{ loadError }}
    </div>

    <div class="console-body">
      <aside class="runs-panel">
        <div class="runs-heading">
          <div>
            <span class="section-kicker">RECENT RUNS</span>
            <strong>最近执行</strong>
          </div>
          <span>{{ filteredTraces.length }}</span>
        </div>

        <div class="filters">
          <div class="status-segments" aria-label="按链路状态筛选">
            <button :class="{ active: !filterStatus }" @click="filterStatus = ''">全部 <b>{{ traces.length }}</b></button>
            <button :class="{ active: filterStatus === 'verified' }" @click="filterStatus = 'verified'">正常 <b>{{ trustCounts.verified }}</b></button>
            <button :class="{ active: filterStatus === 'degraded' }" @click="filterStatus = 'degraded'">告警 <b>{{ trustCounts.degraded }}</b></button>
            <button :class="{ active: filterStatus === 'partial' }" @click="filterStatus = 'partial'">不完整 <b>{{ trustCounts.partial }}</b></button>
          </div>
          <label class="search-field">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
            <input v-model="filterText" placeholder="搜索问题、ID 或 Agent" />
          </label>
          <div class="filter-row">
            <select v-model="filterAgent">
              <option value="">全部 Agent</option>
              <option v-for="agent in uniqueAgents" :key="agent" :value="agent">{{ agentMeta(agent).label }}</option>
            </select>
            <button class="clear-filter" :disabled="!filterAgent && !filterText && !filterStatus" @click="filterAgent = ''; filterText = ''; filterStatus = ''">清除筛选</button>
          </div>
        </div>

        <div class="runs-list">
          <div v-if="listLoading" class="panel-state"><span class="loader" />正在读取执行记录</div>
          <div v-else-if="!filteredTraces.length" class="panel-state">没有匹配的 Trace</div>
          <button
            v-for="trace in filteredTraces"
            :key="trace.trace_id"
            class="run-card"
            :class="{ active: selectedTrace?.trace_id === trace.trace_id }"
            @click="selectTrace(trace.trace_id)"
          >
            <div class="run-card-top">
              <span class="status-beacon" :class="trustClass(trace.status)" />
              <span class="run-result">{{ verdictLabel(trace.verdict) }}</span>
              <span class="run-time">{{ formatTraceTime(trace.started_at) }}</span>
            </div>
            <p v-if="trace.input_preview" class="run-question">{{ trace.input_preview }}</p>
            <div class="agent-flow compact">
              <template v-for="(agent, index) in trace.agents" :key="`${trace.trace_id}-${agent}`">
                <span :style="{ '--agent-color': agentMeta(agent).color }">{{ agentMeta(agent).label }}</span>
                <b v-if="index < trace.agents.length - 1">→</b>
              </template>
              <span v-if="!trace.agents.length">无 Agent 数据</span>
            </div>
            <div class="run-meta">
              <span>{{ formatLatency(trace.latency_ms) }}</span>
              <span>{{ trace.call_count }} 次模型</span>
              <span>{{ trace.tool_count }} 次工具</span>
              <span>{{ formatCost(trace.cost_usd) }}</span>
            </div>
            <div class="run-id">{{ trace.trace_id.slice(0, 8) }} · {{ trace.event_count }} 个事件</div>
          </button>
        </div>
      </aside>

      <main class="trace-detail">
        <div v-if="!selectedTrace && !traceLoading" class="empty-detail">
          <div class="empty-orbit"><span /><span /><span /></div>
          <h2>选择一次执行</h2>
          <p>查看 Agent 如何处理输入、调用模型与工具，以及系统为何结束链路。</p>
        </div>
        <div v-else-if="traceLoading" class="empty-detail"><span class="loader large" /><p>正在还原执行链路…</p></div>

        <template v-else-if="selectedTrace">
          <section class="detail-hero">
            <div class="hero-main">
              <div class="hero-labels">
                <span class="scope-pill">{{ phaseLabel(selectedTrace) }}</span>
                <span class="trust-pill" :class="trustClass(selectedTrace.trust.status)">
                  <i />{{ trustLabel(selectedTrace.trust.status) }} · {{ selectedTrace.trust.score }}
                </span>
              </div>
              <h2>{{ selectedTitle }}</h2>
              <div class="trace-identifiers">
                <span>Trace <code>{{ selectedTrace.trace_id.slice(0, 12) }}</code></span>
                <span>Session <code>{{ selectedTrace.session_id.slice(0, 12) }}</code></span>
                <span>{{ formatTraceTime(selectedTrace.summary.started_at) }} → {{ formatTraceTime(selectedTrace.summary.ended_at) }}</span>
                <button @click="copyTraceId">复制 ID</button>
                <button @click="exportTrace">导出 JSON</button>
                <em v-if="actionNotice">{{ actionNotice }}</em>
              </div>
            </div>

            <div class="outcome-card" :class="selectedTrace.summary.status">
              <span class="section-kicker">OUTCOME</span>
              <strong>{{ verdictLabel(selectedTrace.summary.verdict) }}</strong>
              <p>{{ verdictDescription(selectedTrace.summary.verdict) }}</p>
            </div>
          </section>

          <section class="metric-grid">
            <div class="metric-card primary"><span>端到端耗时</span><strong>{{ formatLatency(selectedTrace.summary.wall_clock_ms) }}</strong><small>从接收请求到链路结束</small></div>
            <div class="metric-card"><span>模型调用</span><strong>{{ selectedTrace.summary.call_count }}</strong><small>{{ formatLatency(selectedTrace.summary.total_latency_ms) }} 累计 · {{ selectedTrace.summary.total_tokens.toLocaleString() }} Token</small></div>
            <div class="metric-card"><span>工具调用</span><strong>{{ selectedTrace.summary.tool_count }}</strong><small>{{ selectedTrace.summary.retrieval_count }} 次检索</small></div>
            <div class="metric-card"><span>Agent</span><strong>{{ selectedTrace.summary.agent_count }}</strong><small>{{ selectedTrace.summary.handoff_count }} 次接力</small></div>
            <div class="metric-card"><span>可验证引用</span><strong>{{ selectedTrace.trust.verified_citation_count }}</strong><small>召回 {{ selectedTrace.trust.retrieved_note_count }} 条笔记</small></div>
            <div class="metric-card"><span>估算成本</span><strong>{{ formatCost(selectedTrace.summary.total_cost_usd) }}</strong><small>{{ selectedTrace.events.length }} 个账本事件</small></div>
          </section>

          <nav class="detail-tabs">
            <button v-for="tabItem in detailTabs" :key="tabItem.id" :class="{ active: activeTab === tabItem.id }" @click="activeTab = tabItem.id">
              {{ tabItem.label }}
              <span v-if="tabItem.id === 'timeline'">{{ selectedTrace.events.length }}</span>
              <span v-if="tabItem.id === 'evidence'">{{ selectedTrace.evidence.retrievals.length + selectedTrace.evidence.citations.length }}</span>
            </button>
          </nav>

          <div class="tab-content">
            <template v-if="activeTab === 'overview'">
              <section class="diagnosis-strip" :class="issueCount ? 'has-issues' : 'healthy'">
                <div class="diagnosis-icon">{{ issueCount ? '!' : '✓' }}</div>
                <div>
                  <span class="section-kicker">QUICK READ</span>
                  <strong>{{ issueCount ? `发现 ${issueCount} 个需要关注的信号` : '这条链路执行完整，未发现结构异常' }}</strong>
                  <p v-if="slowestSpan">主要耗时在 {{ agentMeta(slowestSpan.agentId).label }} 的 {{ slowestSpan.label }}，约 {{ formatLatency(slowestSpan.durationMs) }}。</p>
                  <p v-else>{{ verdictDescription(selectedTrace.summary.verdict) }}</p>
                </div>
                <button v-if="issueCount" @click="activeTab = 'evidence'">查看问题 →</button>
              </section>

              <section class="content-card flow-card">
                <div class="card-heading">
                  <div><span class="section-kicker">EXECUTION FLOW</span><h3>链路瀑布图</h3></div>
                  <div class="flow-legend"><span><i class="model" />模型</span><span><i class="tool" />工具</span><span><i class="handoff" />接力</span></div>
                </div>
                <div class="flow-workspace">
                  <div class="waterfall">
                    <div class="waterfall-axis"><span>开始</span><span>25%</span><span>50%</span><span>75%</span><span>{{ formatLatency(flowDuration) }}</span></div>
                    <button
                      v-for="span in flowSpans"
                      :key="span.id"
                      class="waterfall-row"
                      :class="{ active: selectedSpan?.id === span.id, error: span.status === 'error' }"
                      @click="selectSpan(span)"
                    >
                      <span class="waterfall-label">
                        <b :style="{ color: agentMeta(span.agentId).color }">{{ agentMeta(span.agentId).label }}</b>
                        <span>{{ span.label }}</span>
                      </span>
                      <span class="waterfall-track">
                        <i
                          :class="span.kind"
                          :style="{ left: `${spanOffset(span)}%`, width: `${spanWidth(span)}%`, '--agent-color': agentMeta(span.agentId).color }"
                        />
                      </span>
                      <span class="waterfall-time">{{ span.durationMs > 1 ? formatLatency(span.durationMs) : `#${span.event.sequence}` }}</span>
                    </button>
                  </div>

                  <aside class="event-inspector">
                    <template v-if="selectedSpan">
                      <div class="inspector-heading">
                        <span class="event-kind">{{ selectedSpan.kind.toUpperCase() }}</span>
                        <button aria-label="关闭事件详情" @click="selectedSpan = null">×</button>
                      </div>
                      <h4>{{ selectedSpan.label }}</h4>
                      <p>{{ eventSummary(selectedSpan.endEvent || selectedSpan.event) }}</p>
                      <dl>
                        <div><dt>Agent</dt><dd :style="{ color: agentMeta(selectedSpan.agentId).color }">{{ agentMeta(selectedSpan.agentId).label }}</dd></div>
                        <div><dt>耗时</dt><dd>{{ formatLatency(selectedSpan.durationMs) }}</dd></div>
                        <div><dt>状态</dt><dd>{{ selectedSpan.status || 'ok' }}</dd></div>
                        <div><dt>事件</dt><dd>#{{ selectedSpan.event.sequence }}<template v-if="selectedSpan.endEvent"> → #{{ selectedSpan.endEvent.sequence }}</template></dd></div>
                      </dl>
                      <button class="inspect-raw" @click="activeTab = 'timeline'">在完整时间线中查看 →</button>
                    </template>
                    <template v-else>
                      <div class="inspector-empty"><span>↖</span><strong>选择一个步骤</strong><p>点击左侧任意条带，查看该模型、工具或接力事件的上下文。</p></div>
                    </template>
                  </aside>
                </div>
              </section>

              <div class="overview-grid">
                <section class="content-card execution-card">
                  <div class="card-heading"><div><span class="section-kicker">AGENT PATH</span><h3>执行路径</h3></div><span>{{ selectedTrace.summary.handoff_count }} 次接力</span></div>
                  <div class="agent-path">
                    <template v-for="(agent, index) in selectedTrace.agents" :key="agent.agent_id">
                      <div class="agent-node" :style="{ '--agent-color': agentMeta(agent.agent_id).color }">
                        <div class="agent-avatar">{{ agentMeta(agent.agent_id).label.slice(0, 1) }}</div>
                        <div><strong>{{ agentMeta(agent.agent_id).label }}</strong><span>{{ agentMeta(agent.agent_id).role }}</span></div>
                        <div class="agent-stats"><b>{{ agent.call_count }}</b> 模型 <b>{{ agent.timeline.filter(event => event.event_type === 'tool_end').length }}</b> 工具</div>
                      </div>
                      <div v-if="index < selectedTrace.agents.length - 1" class="path-arrow"><span>handoff</span>→</div>
                    </template>
                    <div v-if="!selectedTrace.agents.length" class="inline-empty">没有可用的 Agent 阶段数据</div>
                  </div>
                </section>

                <section class="content-card reliability-card">
                  <div class="card-heading"><div><span class="section-kicker">RELIABILITY</span><h3>可信度检查</h3></div><strong class="score">{{ selectedTrace.trust.score }}</strong></div>
                  <div class="score-track"><span :style="{ width: `${selectedTrace.trust.score}%` }" /></div>
                  <div class="check-list">
                    <div><span :class="selectedTrace.trust.ledger.valid ? 'check-ok' : 'check-bad'">{{ selectedTrace.trust.ledger.valid ? '✓' : '!' }}</span><p><strong>事件账本</strong><small>{{ selectedTrace.trust.ledger.valid ? '哈希连续，事件未被篡改' : '账本连续性校验失败' }}</small></p></div>
                    <div><span :class="selectedTrace.trust.missing_required_events.length ? 'check-warn' : 'check-ok'">{{ selectedTrace.trust.missing_required_events.length ? '!' : '✓' }}</span><p><strong>必要事件</strong><small>{{ selectedTrace.trust.missing_required_events.length ? `缺少 ${selectedTrace.trust.missing_required_events.join('、')}` : '开始、上下文、判定与结束事件完整' }}</small></p></div>
                    <div><span :class="selectedTrace.trust.open_tool_calls.length ? 'check-bad' : 'check-ok'">{{ selectedTrace.trust.open_tool_calls.length ? '!' : '✓' }}</span><p><strong>工具闭环</strong><small>{{ selectedTrace.trust.open_tool_calls.length ? `${selectedTrace.trust.open_tool_calls.length} 个工具调用未闭合` : '所有工具调用均有返回结果' }}</small></p></div>
                  </div>
                </section>
              </div>

              <section class="content-card key-events-card">
                <div class="card-heading"><div><span class="section-kicker">STORYLINE</span><h3>关键执行过程</h3></div><button @click="activeTab = 'timeline'">查看全部 {{ selectedTrace.events.length }} 个事件 →</button></div>
                <div class="storyline">
                  <div v-for="event in keyTimeline.slice(0, 8)" :key="event.id" class="story-event" :class="`tone-${eventTone(event)}`">
                    <div class="story-index">{{ String(event.sequence).padStart(2, '0') }}</div>
                    <div class="story-line" />
                    <div class="story-copy">
                      <div><strong>{{ eventLabel(event.event_type) }}</strong><span v-if="event.agent_id">{{ agentMeta(event.agent_id).label }}</span><time>{{ formatTraceTime(event.created_at) }}</time></div>
                      <p>{{ eventSummary(event) }}</p>
                    </div>
                  </div>
                </div>
              </section>

              <section v-if="llmEvents.length" class="content-card model-card">
                <div class="card-heading"><div><span class="section-kicker">MODEL CALLS</span><h3>模型调用明细</h3></div></div>
                <div class="model-table">
                  <div class="model-row model-head"><span>Agent / 模型</span><span>输入</span><span>输出</span><span>耗时</span><span>状态</span></div>
                  <div v-for="event in llmEvents" :key="event.id" class="model-row">
                    <span><b :style="{ color: agentMeta(event.agent_id).color }">{{ agentMeta(event.agent_id).label }}</b><small>{{ event.name }}</small></span>
                    <span>{{ (event.payload.input_tokens || 0).toLocaleString() }}</span>
                    <span>{{ (event.payload.output_tokens || 0).toLocaleString() }}</span>
                    <span>{{ formatLatency(event.payload.latency_ms || 0) }}</span>
                    <span class="status-text" :class="event.status">{{ event.status === 'error' ? '失败' : '完成' }}</span>
                  </div>
                </div>
              </section>
            </template>

            <section v-else-if="activeTab === 'timeline'" class="content-card timeline-card">
              <div class="timeline-toolbar">
                <div class="timeline-filters">
                  <button v-for="item in timelineFilters" :key="item.id" :class="{ active: timelineFilter === item.id }" @click="timelineFilter = item.id">
                    {{ item.label }}
                  </button>
                </div>
                <label class="timeline-search">
                  <span>⌕</span><input v-model="timelineSearch" placeholder="搜索事件、Agent 或参数" />
                </label>
                <span>{{ filteredTimeline.length }} / {{ selectedTrace.events.length }} EVENTS</span>
              </div>
              <div class="full-timeline">
                <div v-if="!filteredTimeline.length" class="inline-empty">没有符合当前筛选条件的事件。</div>
                <article v-for="event in filteredTimeline" :key="event.id" class="timeline-event" :class="`tone-${eventTone(event)}`">
                  <div class="event-sequence">#{{ event.sequence }}</div>
                  <div class="event-glyph"><span /></div>
                  <div class="event-body">
                    <div class="event-title-row">
                      <strong>{{ eventLabel(event.event_type) }}</strong>
                      <span v-if="event.agent_id" class="agent-tag" :style="{ '--agent-color': agentMeta(event.agent_id).color }">{{ agentMeta(event.agent_id).label }}</span>
                      <code v-if="event.phase_trace_id">{{ event.phase_trace_id.slice(0, 8) }}</code>
                      <time>{{ formatTraceTime(event.created_at) }}</time>
                    </div>
                    <p>{{ eventSummary(event) }}</p>
                    <details v-if="Object.keys(event.payload || {}).length"><summary>查看事件参数</summary><pre>{{ prettyPayload(event) }}</pre></details>
                  </div>
                </article>
              </div>
            </section>

            <template v-else-if="activeTab === 'evidence'">
              <div class="evidence-grid">
                <section class="content-card">
                  <div class="card-heading"><div><span class="section-kicker">RETRIEVALS</span><h3>检索证据</h3></div><span>{{ selectedTrace.evidence.retrievals.length }}</span></div>
                  <div v-if="!selectedTrace.evidence.retrievals.length" class="inline-empty">本链路没有触发笔记检索。</div>
                  <article v-for="retrieval in selectedTrace.evidence.retrievals" :key="retrieval.id" class="retrieval-card">
                    <div><span class="agent-tag" :style="{ '--agent-color': agentMeta(retrieval.agent_id).color }">{{ agentMeta(retrieval.agent_id).label }}</span><time>#{{ retrieval.sequence }} · {{ formatTraceTime(retrieval.created_at) }}</time></div>
                    <p>{{ eventSummary(retrieval) }}</p>
                    <div v-for="note in selectedNotes(retrieval)" :key="note.note_id" class="note-result">
                      <span><strong>{{ note.title || note.note_id }}</strong><code>{{ note.note_id }}</code></span>
                      <span>相关度 <b>{{ note.ranker?.final_score ?? '—' }}</b></span>
                    </div>
                  </article>
                </section>

                <section class="content-card">
                  <div class="card-heading"><div><span class="section-kicker">CITATIONS</span><h3>引用校验</h3></div><span>{{ selectedTrace.evidence.citations.length }}</span></div>
                  <div v-if="!selectedTrace.evidence.citations.length" class="inline-empty">最终输出中没有检测到可精确验证的 note_id 引用。</div>
                  <div v-for="citation in selectedTrace.evidence.citations" :key="`${citation.sequence}-${citation.note_id}`" class="citation-row">
                    <span class="citation-check">✓</span>
                    <div><strong>{{ citation.note_id }}</strong><small>{{ agentMeta(citation.agent_id).label }} · {{ citation.verification }}</small></div>
                    <span>#{{ citation.sequence }}</span>
                  </div>
                </section>
              </div>

              <section v-if="selectedTrace.trust.structural_issues.length || selectedTrace.trust.missing_required_events.length || selectedTrace.trust.open_tool_calls.length" class="content-card issues-card">
                <div class="card-heading"><div><span class="section-kicker">ISSUES</span><h3>需要关注的问题</h3></div></div>
                <div v-for="issue in selectedTrace.trust.structural_issues" :key="issue" class="issue-row danger"><span>!</span><p><strong>链路结构异常</strong><small>{{ issue }}</small></p></div>
                <div v-for="eventType in selectedTrace.trust.missing_required_events" :key="eventType" class="issue-row warning"><span>!</span><p><strong>缺少必要事件</strong><small>{{ eventLabel(eventType) }}（{{ eventType }}）</small></p></div>
                <div v-for="tool in selectedTrace.trust.open_tool_calls" :key="tool.tool_call_id" class="issue-row danger"><span>!</span><p><strong>工具调用未闭环</strong><small>{{ agentMeta(tool.agent_id).label }} · {{ tool.name }} · {{ tool.tool_call_id }}</small></p></div>
              </section>
            </template>

            <section v-else class="content-card raw-card">
              <details v-for="event in selectedTrace.events" :key="event.id">
                <summary><span>#{{ event.sequence }}</span><strong>{{ event.event_type }}</strong><span>{{ event.agent_id || 'system' }}</span><time>{{ formatTraceTime(event.created_at) }}</time></summary>
                <pre>{{ prettyPayload(event) }}</pre>
                <div class="hash-row"><span>previous</span><code>{{ event.prev_hash || '—' }}</code><span>event</span><code>{{ event.event_hash || '—' }}</code></div>
              </details>
            </section>
          </div>
        </template>
      </main>
    </div>
  </div>
</template>

<style scoped>
.trace-console { --panel: rgba(15, 18, 27, .78); --panel-strong: rgba(20, 24, 35, .94); display: flex; height: 100%; min-height: 0; flex-direction: column; color: var(--text-primary); background: radial-gradient(circle at 72% -10%, rgba(124, 156, 255, .12), transparent 34%), #0b0d13; }
.console-header { display: flex; min-height: 76px; flex-shrink: 0; align-items: center; gap: 28px; border-bottom: 1px solid rgba(255,255,255,.075); padding: 0 24px; background: rgba(11,13,19,.82); backdrop-filter: blur(18px); }
.header-brand { display: flex; align-items: center; gap: 13px; }
.brand-mark { display: flex; height: 38px; width: 38px; align-items: flex-end; justify-content: center; gap: 3px; border: 1px solid rgba(124,156,255,.25); border-radius: 12px; padding-bottom: 10px; background: linear-gradient(145deg, rgba(124,156,255,.16), rgba(184,140,255,.08)); }
.brand-mark span { width: 3px; border-radius: 3px; background: #9aafff; box-shadow: 0 0 10px rgba(124,156,255,.5); }.brand-mark span:nth-child(1){height:8px}.brand-mark span:nth-child(2){height:15px}.brand-mark span:nth-child(3){height:11px}
.eyebrow,.section-kicker { color: #788397; font-size: 9px; font-weight: 700; letter-spacing: .16em; }
.header-brand h1 { margin-top: 2px; font-size: 16px; font-weight: 700; letter-spacing: -.02em; }
.header-health { display: flex; align-items: center; gap: 8px; color: var(--text-tertiary); font-size: 11px; }.health-dot { height: 7px; width: 7px; border-radius: 50%; background: #70e0a3; box-shadow: 0 0 12px rgba(112,224,163,.65); }.header-divider{height:12px;width:1px;background:rgba(255,255,255,.1)}
.header-actions { margin-left: auto; display:flex; gap:8px; }.icon-button,.close-button { display:flex; height:34px; align-items:center; justify-content:center; border:1px solid rgba(255,255,255,.09); border-radius:10px; color:var(--text-secondary); background:rgba(255,255,255,.035); transition:.18s ease; }.icon-button{width:34px}.icon-button svg{width:15px;stroke-width:1.8}.close-button{gap:8px;padding:0 12px;font-size:11px}.close-button kbd{color:var(--text-tertiary);font-size:9px}.icon-button:hover,.close-button:hover{border-color:rgba(124,156,255,.35);background:rgba(124,156,255,.08);color:#dce3ff}
.error-banner { display:flex; gap:8px; align-items:center; border-bottom:1px solid rgba(242,123,123,.2); padding:9px 24px; color:#f59696; background:rgba(239,68,68,.08); font-size:11px }.error-banner span{display:grid;width:17px;height:17px;place-items:center;border-radius:50%;background:rgba(239,68,68,.18);font-weight:800}
.console-body { display:flex; min-height:0; flex:1; }.runs-panel { display:flex; width:326px; min-width:326px; flex-direction:column; border-right:1px solid rgba(255,255,255,.075); background:rgba(12,14,21,.72) }.runs-heading { display:flex; align-items:center; justify-content:space-between; padding:21px 18px 14px }.runs-heading div{display:flex;flex-direction:column;gap:3px}.runs-heading strong{font-size:13px}.runs-heading>span{display:grid;height:23px;min-width:23px;place-items:center;border-radius:7px;color:var(--text-tertiary);background:rgba(255,255,255,.05);font-size:10px}
.filters{padding:0 14px 14px;border-bottom:1px solid rgba(255,255,255,.065)}.search-field{display:flex;height:36px;align-items:center;gap:8px;border:1px solid rgba(255,255,255,.085);border-radius:10px;padding:0 10px;background:rgba(255,255,255,.025)}.search-field:focus-within{border-color:rgba(124,156,255,.42);box-shadow:0 0 0 3px rgba(124,156,255,.06)}.search-field svg{width:14px;color:#697387;stroke-width:1.8}.search-field input{min-width:0;flex:1;background:transparent;color:var(--text-primary);font-size:11px;outline:none}.search-field input::placeholder{color:#626b7c}.filter-row{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:7px}.filter-row select{height:31px;border:1px solid rgba(255,255,255,.075);border-radius:8px;padding:0 8px;background:#12151e;color:var(--text-secondary);font-size:10px;outline:none}
.runs-list{min-height:0;flex:1;overflow-y:auto;padding:8px}.panel-state{display:flex;min-height:140px;align-items:center;justify-content:center;gap:9px;color:var(--text-tertiary);font-size:11px}.loader{width:14px;height:14px;border:2px solid rgba(124,156,255,.18);border-top-color:#8ca5ff;border-radius:50%;animation:spin .8s linear infinite}.loader.large{width:25px;height:25px}.run-card{width:100%;border:1px solid transparent;border-radius:12px;padding:12px;text-align:left;transition:.16s ease}.run-card+.run-card{margin-top:3px}.run-card:hover{background:rgba(255,255,255,.035)}.run-card.active{border-color:rgba(124,156,255,.22);background:linear-gradient(100deg,rgba(124,156,255,.1),rgba(124,156,255,.035));box-shadow:inset 2px 0 #7c9cff}.run-card-top{display:flex;align-items:center;gap:7px}.status-beacon{width:7px;height:7px;border-radius:50%}.run-result{font-size:11px;font-weight:650}.run-time{margin-left:auto;color:var(--text-tertiary);font-size:9px}.agent-flow{display:flex;align-items:center;gap:5px}.agent-flow.compact{margin-top:10px}.agent-flow span{color:var(--agent-color);font-size:10px;font-weight:650}.agent-flow b{color:#4f5869;font-size:9px}.run-meta{display:flex;gap:10px;margin-top:8px;color:var(--text-tertiary);font-size:9px}.run-id{margin-top:7px;color:#50596b;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:8px;letter-spacing:.03em}
.run-question{display:-webkit-box;margin-top:8px;overflow:hidden;color:var(--text-secondary);font-size:10px;line-height:1.45;-webkit-box-orient:vertical;-webkit-line-clamp:2}
.trace-detail{min-width:0;flex:1;overflow-y:auto}.empty-detail{display:flex;height:100%;align-items:center;justify-content:center;flex-direction:column;color:var(--text-tertiary);text-align:center}.empty-detail h2{margin-top:18px;color:var(--text-secondary);font-size:15px}.empty-detail p{max-width:360px;margin-top:7px;font-size:11px;line-height:1.7}.empty-orbit{position:relative;width:70px;height:70px;border:1px solid rgba(124,156,255,.16);border-radius:50%}.empty-orbit:before,.empty-orbit:after{content:"";position:absolute;border:1px solid rgba(124,156,255,.1);border-radius:50%;inset:10px}.empty-orbit:after{inset:24px;background:rgba(124,156,255,.14);box-shadow:0 0 24px rgba(124,156,255,.22)}.empty-orbit span{position:absolute;width:6px;height:6px;border-radius:50%;background:#7c9cff}.empty-orbit span:nth-child(1){top:8px;left:31px}.empty-orbit span:nth-child(2){bottom:14px;right:5px}.empty-orbit span:nth-child(3){bottom:8px;left:15px}
.detail-hero{display:flex;gap:24px;padding:26px 30px 22px}.hero-main{min-width:0;flex:1}.hero-labels{display:flex;align-items:center;gap:7px}.scope-pill,.trust-pill{display:inline-flex;height:23px;align-items:center;border-radius:7px;padding:0 8px;font-size:9px;font-weight:650}.scope-pill{color:#aeb8ca;background:rgba(255,255,255,.055)}.trust-pill{gap:5px}.trust-pill i{width:5px;height:5px;border-radius:50%;background:currentColor}.hero-main h2{max-width:800px;margin-top:13px;font-size:20px;font-weight:650;line-height:1.4;letter-spacing:-.025em}.trace-identifiers{display:flex;flex-wrap:wrap;gap:14px;margin-top:13px;color:var(--text-tertiary);font-size:9px}.trace-identifiers code{color:#8590a4}.outcome-card{width:260px;flex-shrink:0;border:1px solid rgba(112,224,163,.16);border-radius:14px;padding:14px 16px;background:rgba(112,224,163,.045)}.outcome-card strong{display:block;margin-top:7px;color:#8ae9b2;font-size:14px}.outcome-card p{margin-top:5px;color:var(--text-tertiary);font-size:10px;line-height:1.55}.outcome-card.error,.outcome-card.incomplete{border-color:rgba(245,185,66,.18);background:rgba(245,185,66,.05)}.outcome-card.error strong,.outcome-card.incomplete strong{color:#f5b942}
.metric-grid{display:grid;grid-template-columns:repeat(6,minmax(110px,1fr));gap:8px;padding:0 30px 22px}.metric-card{min-width:0;border:1px solid rgba(255,255,255,.065);border-radius:12px;padding:12px;background:rgba(255,255,255,.025)}.metric-card.primary{border-color:rgba(124,156,255,.18);background:rgba(124,156,255,.055)}.metric-card>span{display:block;color:var(--text-tertiary);font-size:9px}.metric-card strong{display:block;margin-top:5px;font-size:17px;font-weight:650;letter-spacing:-.03em}.metric-card small{display:block;margin-top:3px;color:#616b7d;font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.detail-tabs{position:sticky;top:0;z-index:5;display:flex;gap:22px;border-top:1px solid rgba(255,255,255,.055);border-bottom:1px solid rgba(255,255,255,.075);padding:0 30px;background:rgba(11,13,19,.9);backdrop-filter:blur(14px)}.detail-tabs button{position:relative;height:45px;color:var(--text-tertiary);font-size:10px;font-weight:600}.detail-tabs button.active{color:#dbe2f0}.detail-tabs button.active:after{content:"";position:absolute;right:0;bottom:-1px;left:0;height:2px;border-radius:2px;background:#7c9cff;box-shadow:0 -3px 10px rgba(124,156,255,.3)}.detail-tabs button span{margin-left:5px;border-radius:5px;padding:1px 5px;background:rgba(255,255,255,.06);font-size:8px}.tab-content{padding:20px 30px 34px}.overview-grid,.evidence-grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(280px,.8fr);gap:12px}.content-card{border:1px solid rgba(255,255,255,.07);border-radius:15px;background:var(--panel);overflow:hidden}.card-heading{display:flex;align-items:center;justify-content:space-between;padding:16px 17px 13px}.card-heading h3{margin-top:3px;font-size:12px}.card-heading>span,.card-heading>button{color:var(--text-tertiary);font-size:9px}.card-heading>button:hover{color:#9bb0ff}.score{color:#83e4ad;font-size:18px}
.agent-path{display:flex;align-items:stretch;gap:9px;padding:2px 17px 17px;overflow-x:auto}.agent-node{display:flex;min-width:190px;flex:1;align-items:center;gap:10px;border:1px solid color-mix(in srgb,var(--agent-color) 18%,transparent);border-radius:11px;padding:11px;background:color-mix(in srgb,var(--agent-color) 5%,transparent)}.agent-avatar{display:grid;width:30px;height:30px;flex-shrink:0;place-items:center;border-radius:9px;color:var(--agent-color);background:color-mix(in srgb,var(--agent-color) 14%,transparent);font-size:11px;font-weight:750}.agent-node>div:nth-child(2){display:flex;min-width:0;flex-direction:column}.agent-node strong{font-size:10px}.agent-node span{margin-top:2px;color:var(--text-tertiary);font-size:8px}.agent-stats{margin-left:auto;color:var(--text-tertiary);font-size:8px;white-space:nowrap}.agent-stats b{color:var(--text-secondary)}.path-arrow{display:flex;min-width:34px;align-items:center;justify-content:center;flex-direction:column;color:#5e687a;font-size:12px}.path-arrow span{font-size:7px;letter-spacing:.04em}
.score-track{height:4px;margin:2px 17px 13px;border-radius:4px;background:rgba(255,255,255,.055);overflow:hidden}.score-track span{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,#6ed8ad,#8ca5ff)}.check-list{padding:0 17px 13px}.check-list>div{display:flex;gap:9px;padding:9px 0;border-top:1px solid rgba(255,255,255,.05)}.check-list>div>span{display:grid;width:18px;height:18px;flex-shrink:0;place-items:center;border-radius:50%;font-size:9px;font-weight:800}.check-ok{color:#79e2a7;background:rgba(112,224,163,.11)}.check-warn{color:#f5b942;background:rgba(245,185,66,.11)}.check-bad{color:#f27b7b;background:rgba(239,68,68,.11)}.check-list p{display:flex;flex-direction:column}.check-list strong{font-size:9px}.check-list small{margin-top:2px;color:var(--text-tertiary);font-size:8px;line-height:1.4}
.key-events-card,.model-card,.issues-card{margin-top:12px}.storyline{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:24px;padding:0 17px 16px}.story-event{display:grid;grid-template-columns:25px 1px minmax(0,1fr);gap:9px;min-height:59px}.story-index{padding-top:3px;color:#687286;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:8px}.story-line{position:relative;background:rgba(255,255,255,.075)}.story-line:before{content:"";position:absolute;top:3px;left:-3px;width:7px;height:7px;border:2px solid #151924;border-radius:50%;background:#707b90}.tone-info .story-line:before,.tone-info .event-glyph span{background:#7c9cff}.tone-success .story-line:before,.tone-success .event-glyph span{background:#70e0a3}.tone-warning .story-line:before,.tone-warning .event-glyph span{background:#f5b942}.tone-danger .story-line:before,.tone-danger .event-glyph span{background:#f27b7b}.story-copy{padding-bottom:13px}.story-copy>div{display:flex;align-items:center;gap:7px}.story-copy strong{font-size:9px}.story-copy span{border-radius:5px;padding:2px 5px;color:var(--text-tertiary);background:rgba(255,255,255,.045);font-size:8px}.story-copy time{margin-left:auto;color:#525c6e;font-size:8px}.story-copy p{margin-top:5px;color:var(--text-secondary);font-size:9px;line-height:1.45}
.model-table{padding:0 8px 8px}.model-row{display:grid;grid-template-columns:minmax(180px,1fr) 90px 90px 90px 70px;align-items:center;min-height:43px;border-top:1px solid rgba(255,255,255,.05);padding:0 10px;color:var(--text-secondary);font-size:9px}.model-row>span:first-child{display:flex;flex-direction:column}.model-row small{margin-top:2px;color:var(--text-tertiary);font-size:8px}.model-head{min-height:30px;color:#606a7d;font-size:8px;text-transform:uppercase;letter-spacing:.08em}.status-text{color:#70e0a3}.status-text.error{color:#f27b7b}
.timeline-toolbar{display:flex;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,.06);padding:12px 17px;color:var(--text-tertiary);font-size:8px}.full-timeline{padding:8px 16px 16px}.timeline-event{display:grid;grid-template-columns:36px 16px minmax(0,1fr);gap:8px}.event-sequence{padding-top:15px;color:#596376;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:8px}.event-glyph{position:relative;display:flex;justify-content:center}.event-glyph:after{content:"";position:absolute;top:0;bottom:0;width:1px;background:rgba(255,255,255,.07)}.event-glyph span{z-index:1;width:8px;height:8px;margin-top:16px;border:2px solid #171b25;border-radius:50%;background:#737d90}.event-body{min-width:0;border-bottom:1px solid rgba(255,255,255,.05);padding:12px 0}.event-title-row{display:flex;align-items:center;gap:7px}.event-title-row strong{font-size:10px}.event-title-row code{color:#667186;font-size:8px}.event-title-row time{margin-left:auto;color:#566073;font-size:8px}.agent-tag{display:inline-flex;border-radius:5px;padding:2px 6px;color:var(--agent-color);background:color-mix(in srgb,var(--agent-color) 10%,transparent);font-size:8px;font-weight:650}.event-body>p{margin-top:6px;color:var(--text-secondary);font-size:9px;line-height:1.55}.event-body details{margin-top:7px}.event-body summary{cursor:pointer;color:#687388;font-size:8px}.event-body pre,.raw-card pre{margin-top:7px;border-radius:8px;padding:10px;background:#0b0d13;color:#8f9aaf;font-size:8px;line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere}
.inline-empty{margin:0 17px 17px;border:1px dashed rgba(255,255,255,.08);border-radius:10px;padding:18px;color:var(--text-tertiary);font-size:9px;text-align:center}.retrieval-card{margin:0 14px 12px;border:1px solid rgba(255,255,255,.055);border-radius:11px;padding:12px;background:rgba(255,255,255,.018)}.retrieval-card>div:first-child{display:flex;align-items:center}.retrieval-card time{margin-left:auto;color:var(--text-tertiary);font-size:8px}.retrieval-card>p{margin:9px 0;color:var(--text-secondary);font-size:9px}.note-result{display:flex;align-items:center;justify-content:space-between;border-top:1px solid rgba(255,255,255,.05);padding:8px 0;color:var(--text-tertiary);font-size:8px}.note-result>span:first-child{display:flex;min-width:0;flex-direction:column}.note-result strong{max-width:280px;color:var(--text-secondary);font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.note-result code{margin-top:2px;color:#596478}.note-result b{color:#9fb0d2}.citation-row{display:grid;grid-template-columns:23px minmax(0,1fr) auto;gap:9px;align-items:center;margin:0 14px;padding:10px 2px;border-top:1px solid rgba(255,255,255,.05)}.citation-check{display:grid;width:20px;height:20px;place-items:center;border-radius:50%;color:#70e0a3;background:rgba(112,224,163,.1);font-size:9px}.citation-row div{display:flex;min-width:0;flex-direction:column}.citation-row strong{overflow:hidden;text-overflow:ellipsis;font-size:9px}.citation-row small,.citation-row>span:last-child{margin-top:2px;color:var(--text-tertiary);font-size:8px}.issue-row{display:flex;gap:10px;margin:0 15px;padding:11px 0;border-top:1px solid rgba(255,255,255,.05)}.issue-row>span{display:grid;width:20px;height:20px;place-items:center;border-radius:6px;font-size:10px;font-weight:800}.issue-row.warning>span{color:#f5b942;background:rgba(245,185,66,.1)}.issue-row.danger>span{color:#f27b7b;background:rgba(239,68,68,.1)}.issue-row p{display:flex;flex-direction:column}.issue-row strong{font-size:9px}.issue-row small{margin-top:3px;color:var(--text-tertiary);font-size:8px}
.raw-card details{border-bottom:1px solid rgba(255,255,255,.055);padding:0 15px}.raw-card summary{display:grid;grid-template-columns:40px 150px 120px 1fr;align-items:center;min-height:42px;cursor:pointer;color:var(--text-tertiary);font-size:9px}.raw-card summary strong{color:var(--text-secondary)}.raw-card summary time{text-align:right}.raw-card pre{margin-bottom:10px}.hash-row{display:grid;grid-template-columns:55px minmax(0,1fr);gap:5px 9px;margin-bottom:12px;color:#566073;font-size:8px}.hash-row code{overflow-wrap:anywhere;color:#778297}
.trust-verified{color:#70e0a3;background:rgba(112,224,163,.1)}.trust-degraded{color:#f5b942;background:rgba(245,185,66,.1)}.trust-partial{color:#aab4c3;background:rgba(148,163,184,.1)}.trust-compromised{color:#f27b7b;background:rgba(239,68,68,.1)}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:1100px){.metric-grid{grid-template-columns:repeat(3,1fr)}.overview-grid,.evidence-grid{grid-template-columns:1fr}.runs-panel{width:290px;min-width:290px}.storyline{grid-template-columns:1fr}}
@media(max-width:760px){.console-header{min-height:64px;padding:0 14px}.header-health{display:none}.runs-panel{width:100%;min-width:0;max-height:240px;border-right:0;border-bottom:1px solid rgba(255,255,255,.075)}.console-body{flex-direction:column}.detail-hero{padding:20px;flex-direction:column}.outcome-card{width:auto}.metric-grid{grid-template-columns:repeat(2,1fr);padding:0 20px 18px}.detail-tabs{padding:0 20px;gap:14px}.tab-content{padding:16px 20px 28px}.model-row{grid-template-columns:minmax(120px,1fr) 55px 55px 60px}.model-row>span:last-child{display:none}}
.diagnosis-strip{display:flex;align-items:center;gap:12px;margin-bottom:12px;border:1px solid rgba(112,224,163,.16);border-radius:14px;padding:13px 15px;background:linear-gradient(90deg,rgba(112,224,163,.07),rgba(112,224,163,.025))}.diagnosis-strip.has-issues{border-color:rgba(245,185,66,.2);background:linear-gradient(90deg,rgba(245,185,66,.08),rgba(245,185,66,.02))}.diagnosis-icon{display:grid;width:30px;height:30px;flex-shrink:0;place-items:center;border-radius:9px;color:#76e2a5;background:rgba(112,224,163,.12);font-size:13px;font-weight:800}.has-issues .diagnosis-icon{color:#f5c65f;background:rgba(245,185,66,.12)}.diagnosis-strip>div:nth-child(2){min-width:0;flex:1}.diagnosis-strip strong{display:block;margin-top:3px;font-size:11px}.diagnosis-strip p{margin-top:3px;color:var(--text-tertiary);font-size:9px;line-height:1.45}.diagnosis-strip button{border:1px solid rgba(245,185,66,.18);border-radius:8px;padding:7px 9px;color:#e8c875;background:rgba(245,185,66,.06);font-size:9px}
.flow-card{margin-bottom:12px}.flow-legend{display:flex;gap:11px;color:var(--text-tertiary);font-size:8px}.flow-legend span{display:flex;align-items:center;gap:4px}.flow-legend i{width:12px;height:3px;border-radius:3px;background:#7c9cff}.flow-legend i.tool{background:#6dd6c0}.flow-legend i.handoff{background:#b88cff}.flow-workspace{display:grid;grid-template-columns:minmax(460px,1fr) 250px;border-top:1px solid rgba(255,255,255,.055)}.waterfall{min-width:0;padding:10px 12px 14px}.waterfall-axis{display:grid;grid-template-columns:repeat(5,1fr);margin:0 55px 7px 164px;color:#4f596b;font-size:7px}.waterfall-axis span:not(:first-child){text-align:right}.waterfall-row{display:grid;width:100%;grid-template-columns:152px minmax(200px,1fr) 45px;gap:10px;align-items:center;min-height:34px;border-radius:7px;padding:0 5px;text-align:left;transition:.14s ease}.waterfall-row:hover,.waterfall-row.active{background:rgba(124,156,255,.07)}.waterfall-row.active{box-shadow:inset 2px 0 #7c9cff}.waterfall-label{display:flex;min-width:0;align-items:center;gap:7px}.waterfall-label b{width:62px;overflow:hidden;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.waterfall-label>span{overflow:hidden;color:var(--text-secondary);font-size:9px;text-overflow:ellipsis;white-space:nowrap}.waterfall-track{position:relative;height:24px;border-left:1px solid rgba(255,255,255,.08);border-right:1px solid rgba(255,255,255,.04);background:repeating-linear-gradient(90deg,transparent,transparent calc(25% - 1px),rgba(255,255,255,.045) 25%)}.waterfall-track i{position:absolute;top:8px;height:8px;min-width:5px;border-radius:3px;background:var(--agent-color);box-shadow:0 0 12px color-mix(in srgb,var(--agent-color) 25%,transparent);opacity:.82}.waterfall-track i.tool,.waterfall-track i.retrieval{height:6px;top:9px;background:#6dd6c0}.waterfall-track i.handoff{height:10px;top:7px;background:#b88cff}.waterfall-row.error .waterfall-track i{background:#f27b7b}.waterfall-time{text-align:right;color:#687286;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:8px}
.event-inspector{min-height:280px;border-left:1px solid rgba(255,255,255,.06);padding:15px;background:rgba(255,255,255,.015)}.inspector-heading{display:flex;align-items:center;justify-content:space-between}.event-kind{border-radius:5px;padding:3px 6px;color:#9bb0ff;background:rgba(124,156,255,.1);font-size:8px}.inspector-heading button{display:grid;width:23px;height:23px;place-items:center;border-radius:6px;color:var(--text-tertiary);font-size:15px}.event-inspector h4{margin-top:13px;font-size:12px}.event-inspector>p{margin-top:7px;color:var(--text-secondary);font-size:9px;line-height:1.55}.event-inspector dl{margin-top:14px;border-top:1px solid rgba(255,255,255,.06)}.event-inspector dl div{display:flex;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,.05);padding:8px 0;font-size:8px}.event-inspector dt{color:var(--text-tertiary)}.event-inspector dd{color:var(--text-secondary)}.inspect-raw{margin-top:13px;color:#92a8ff;font-size:8px}.inspector-empty{display:flex;height:245px;align-items:center;justify-content:center;flex-direction:column;text-align:center}.inspector-empty>span{display:grid;width:32px;height:32px;place-items:center;border-radius:9px;color:#8298eb;background:rgba(124,156,255,.08);font-size:15px}.inspector-empty strong{margin-top:12px;font-size:10px}.inspector-empty p{max-width:180px;margin-top:6px;color:var(--text-tertiary);font-size:8px;line-height:1.55}
.status-segments{display:grid;grid-template-columns:repeat(4,1fr);gap:3px;margin-bottom:8px;border-radius:9px;padding:3px;background:rgba(255,255,255,.035)}.status-segments button{display:flex;height:27px;align-items:center;justify-content:center;gap:4px;border-radius:7px;color:var(--text-tertiary);font-size:8px}.status-segments button.active{color:#dce3f2;background:rgba(124,156,255,.12);box-shadow:0 1px 5px rgba(0,0,0,.2)}.status-segments b{color:#6d788b;font-size:7px}.clear-filter{height:31px;border:1px solid rgba(255,255,255,.075);border-radius:8px;color:var(--text-tertiary);font-size:8px}.clear-filter:not(:disabled):hover{color:#aebffb;border-color:rgba(124,156,255,.24)}.clear-filter:disabled{opacity:.35}
.health-dot.live{background:#f5b942;animation:live-pulse 1.4s ease-in-out infinite}.trace-identifiers button{border-radius:5px;padding:2px 5px;color:#91a8ff;background:rgba(124,156,255,.07);font-size:8px}.trace-identifiers button:hover{background:rgba(124,156,255,.13)}.trace-identifiers em{color:#70e0a3;font-size:8px;font-style:normal}.timeline-toolbar{gap:12px;align-items:center}.timeline-filters{display:flex;gap:3px}.timeline-filters button{border-radius:6px;padding:5px 7px;color:var(--text-tertiary);font-size:8px}.timeline-filters button.active{color:#dce4f5;background:rgba(124,156,255,.12)}.timeline-search{display:flex;height:28px;min-width:190px;flex:1;align-items:center;gap:6px;border:1px solid rgba(255,255,255,.07);border-radius:7px;padding:0 8px;background:rgba(255,255,255,.02)}.timeline-search span{font-size:11px}.timeline-search input{min-width:0;flex:1;background:transparent;color:var(--text-secondary);font-size:8px;outline:none}.timeline-search input::placeholder{color:#596376}@keyframes live-pulse{0%,100%{box-shadow:0 0 0 0 rgba(245,185,66,.15)}50%{box-shadow:0 0 0 5px rgba(245,185,66,0)}}
@media(max-width:1100px){.flow-workspace{grid-template-columns:1fr}.event-inspector{min-height:0;border-top:1px solid rgba(255,255,255,.06);border-left:0}.inspector-empty{height:100px}}
@media(max-width:760px){.timeline-toolbar{align-items:stretch;flex-direction:column}.timeline-filters{overflow-x:auto}.timeline-search{width:100%}}
</style>
