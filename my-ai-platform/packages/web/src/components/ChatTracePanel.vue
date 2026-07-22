<script setup lang="ts">
import { computed } from "vue";
import type { TraceData } from "../composables/useChatTrace";
import {
  agentMeta,
  buildTraceSpans,
  formatCost,
  formatLatency,
  trustLabel,
  verdictDescription,
  verdictLabel,
} from "../trace/model";

const props = defineProps<{
  traceId: string;
  phaseTraceLabel: string | null;
  traceData: TraceData | null;
  traceLoading: boolean;
  traceExpanded: boolean;
}>();

defineEmits<{ toggle: []; reset: [] }>();

const visibleSpans = computed(() => props.traceData ? buildTraceSpans(props.traceData.events).slice(0, 8) : []);
const spanStart = computed(() => visibleSpans.value[0]?.startMs || 0);
const spanDuration = computed(() => {
  if (!visibleSpans.value.length) return 1;
  const end = Math.max(...visibleSpans.value.map((span) => span.startMs + span.durationMs));
  return Math.max(1, end - spanStart.value);
});

function spanStyle(span: (typeof visibleSpans.value)[number]) {
  const left = Math.max(0, Math.min(94, ((span.startMs - spanStart.value) / spanDuration.value) * 100));
  const width = Math.max(2, Math.min(100 - left, (span.durationMs / spanDuration.value) * 100));
  return { left: `${left}%`, width: `${width}%`, "--agent-color": agentMeta(span.agentId).color };
}

const flowLabel = computed(() => {
  if (!props.traceData?.agents.length) return "正在等待执行数据";
  return props.traceData.agents.map((agent) => agentMeta(agent.agent_id).label).join(" → ");
});

function trustClass(status: string): string {
  return `trust-${status}`;
}
</script>

<template>
  <div class="chat-trace-wrap">
    <div v-if="phaseTraceLabel" class="phase-row">
      <span>当前查看单个 Agent 阶段</span>
      <code>{{ phaseTraceLabel }}</code>
      <button @click.stop="$emit('reset')">返回完整链路</button>
    </div>

    <section class="chat-trace-card" :class="{ open: traceExpanded }">
      <button class="trace-summary-button" @click="$emit('toggle')">
        <span class="trace-symbol"><i /><i /><i /></span>
        <span class="summary-copy">
          <span class="summary-label">本次执行 Trace</span>
          <strong>{{ flowLabel }}</strong>
        </span>

        <template v-if="traceData">
          <span class="summary-status" :class="trustClass(traceData.trust.status)">
            <i />{{ trustLabel(traceData.trust.status) }} {{ traceData.trust.score }}
          </span>
          <span class="summary-metric"><small>耗时</small>{{ formatLatency(traceData.summary.total_latency_ms) }}</span>
          <span class="summary-metric"><small>模型</small>{{ traceData.summary.call_count }} 次</span>
          <span class="summary-metric"><small>工具</small>{{ traceData.summary.tool_count }} 次</span>
          <span class="summary-metric"><small>成本</small>{{ formatCost(traceData.summary.total_cost_usd) }}</span>
        </template>
        <span v-else class="summary-loading">{{ traceLoading ? "正在还原链路…" : "展开查看执行过程" }}</span>

        <svg class="trace-chevron" :class="{ open: traceExpanded }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      <div v-if="traceExpanded && traceData" class="trace-expanded">
        <div class="outcome-row">
          <div>
            <span class="section-kicker">OUTCOME</span>
            <strong>{{ verdictLabel(traceData.summary.verdict) }}</strong>
            <p>{{ verdictDescription(traceData.summary.verdict) }}</p>
          </div>
          <div class="token-stat"><span>{{ traceData.summary.total_tokens.toLocaleString() }}</span><small>Token</small></div>
          <div class="token-stat"><span>{{ traceData.summary.retrieval_count }}</span><small>检索</small></div>
          <div class="token-stat"><span>{{ traceData.trust.verified_citation_count }}</span><small>引用验证</small></div>
        </div>

        <div class="agent-route">
          <template v-for="(agent, index) in traceData.agents" :key="agent.agent_id">
            <div class="agent-stage" :style="{ '--agent-color': agentMeta(agent.agent_id).color }">
              <span class="agent-dot">{{ agentMeta(agent.agent_id).label.slice(0, 1) }}</span>
              <div><strong>{{ agentMeta(agent.agent_id).label }}</strong><small>{{ agentMeta(agent.agent_id).role }}</small></div>
              <span class="agent-count">{{ agent.call_count }} 模型 · {{ agent.timeline.filter(event => event.event_type === 'tool_end').length }} 工具</span>
            </div>
            <span v-if="index < traceData.agents.length - 1" class="route-arrow">→</span>
          </template>
        </div>

        <div class="mini-waterfall">
          <div class="timeline-heading"><span>执行链路</span><small>{{ visibleSpans.length }} 个关键步骤 · 共 {{ traceData.events.length }} 个事件</small></div>
          <div class="mini-axis"><span>开始</span><span>{{ formatLatency(spanDuration) }}</span></div>
          <div v-for="span in visibleSpans" :key="span.id" class="mini-span">
            <span class="mini-span-label"><b :style="{ color: agentMeta(span.agentId).color }">{{ agentMeta(span.agentId).label }}</b>{{ span.label }}</span>
            <span class="mini-span-track"><i :class="span.kind" :style="spanStyle(span)" /></span>
            <span class="mini-span-time">{{ span.durationMs > 1 ? formatLatency(span.durationMs) : `#${span.event.sequence}` }}</span>
          </div>
        </div>

        <div v-if="traceData.trust.status !== 'verified'" class="trace-warning">
          <span>!</span>
          <p><strong>这条链路需要关注</strong>{{ traceData.trust.claim }}<template v-if="traceData.trust.missing_required_events.length"> · 缺少 {{ traceData.trust.missing_required_events.join("、") }}</template></p>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.chat-trace-wrap { width: min(900px, calc(100% - 32px)); margin: 0 auto 12px; flex-shrink: 0; }
.phase-row { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; color: var(--text-tertiary); font-size: 10px; }
.phase-row code { border-radius: 6px; padding: 2px 6px; background: rgba(255,255,255,.055); color: var(--text-secondary); font-size: 9px; }
.phase-row button { margin-left: auto; color: #91a8ff; font-size: 10px; }
.chat-trace-card { overflow: hidden; border: 1px solid rgba(255,255,255,.09); border-radius: 16px; background: linear-gradient(135deg, rgba(20,24,35,.9), rgba(15,18,27,.78)); box-shadow: 0 12px 30px rgba(0,0,0,.18); }
.chat-trace-card.open { border-color: rgba(124,156,255,.2); }
.trace-summary-button { display: flex; width: 100%; min-height: 64px; align-items: center; gap: 13px; padding: 10px 14px; text-align: left; }
.trace-symbol { display: flex; width: 34px; height: 34px; flex-shrink: 0; align-items: flex-end; justify-content: center; gap: 3px; border-radius: 10px; padding-bottom: 9px; background: rgba(124,156,255,.1); }
.trace-symbol i { width: 3px; border-radius: 3px; background: #8ea6ff; }.trace-symbol i:nth-child(1){height:7px}.trace-symbol i:nth-child(2){height:14px}.trace-symbol i:nth-child(3){height:10px}
.summary-copy { display: flex; min-width: 150px; flex-direction: column; }.summary-label { color: var(--text-tertiary); font-size: 8px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }.summary-copy strong { margin-top: 4px; overflow: hidden; color: var(--text-primary); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.summary-status { display: inline-flex; align-items: center; gap: 5px; border-radius: 7px; padding: 5px 8px; font-size: 9px; font-weight: 650; }.summary-status i { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.summary-metric { display: flex; min-width: 50px; flex-direction: column; color: var(--text-secondary); font-size: 10px; }.summary-metric small { margin-bottom: 2px; color: var(--text-tertiary); font-size: 8px; }.summary-loading { color: var(--text-tertiary); font-size: 9px; }.trace-chevron { width: 13px; height: 13px; margin-left: auto; color: var(--text-tertiary); transition: transform .18s ease; }.trace-chevron.open { transform: rotate(180deg); }
.trace-expanded { border-top: 1px solid rgba(255,255,255,.07); padding: 14px; }
.outcome-row { display: grid; grid-template-columns:minmax(0,1fr) repeat(3,72px); gap: 10px; align-items: center; border: 1px solid rgba(112,224,163,.12); border-radius: 11px; padding: 12px; background: rgba(112,224,163,.035); }.section-kicker { color: #707b8e; font-size: 8px; font-weight: 700; letter-spacing: .14em; }.outcome-row>div:first-child strong { display: block; margin-top: 4px; color: #84e5ad; font-size: 11px; }.outcome-row p { margin-top: 3px; color: var(--text-tertiary); font-size: 9px; line-height: 1.45; }.token-stat { display: flex; align-items: center; flex-direction: column; border-left: 1px solid rgba(255,255,255,.07); }.token-stat span { font-size: 13px; font-weight: 650; }.token-stat small { margin-top: 2px; color: var(--text-tertiary); font-size: 8px; }
.agent-route { display: flex; align-items: center; gap: 7px; margin-top: 10px; overflow-x: auto; }.agent-stage { display: flex; min-width: 190px; flex: 1; align-items: center; gap: 8px; border: 1px solid color-mix(in srgb,var(--agent-color) 16%,transparent); border-radius: 10px; padding: 9px; background: color-mix(in srgb,var(--agent-color) 4%,transparent); }.agent-dot { display: grid; width: 27px; height: 27px; flex-shrink: 0; place-items: center; border-radius: 8px; color: var(--agent-color); background: color-mix(in srgb,var(--agent-color) 12%,transparent); font-size: 9px; font-weight: 750; }.agent-stage div { display: flex; flex-direction: column; }.agent-stage strong { font-size: 9px; }.agent-stage small { margin-top: 2px; color: var(--text-tertiary); font-size: 8px; }.agent-count { margin-left: auto; color: var(--text-tertiary); font-size: 8px; white-space: nowrap; }.route-arrow { color: #596477; font-size: 11px; }
.mini-waterfall{margin-top:12px;border-top:1px solid rgba(255,255,255,.06);padding-top:10px}.timeline-heading{display:flex;justify-content:space-between;margin-bottom:4px;color:var(--text-secondary);font-size:9px}.timeline-heading small{color:var(--text-tertiary);font-size:8px}.mini-axis{display:flex;justify-content:space-between;margin:7px 48px 3px 150px;color:#525c6d;font-size:7px}.mini-span{display:grid;grid-template-columns:140px minmax(160px,1fr) 40px;gap:9px;align-items:center;min-height:25px}.mini-span-label{display:flex;min-width:0;gap:6px;overflow:hidden;color:var(--text-secondary);font-size:8px;text-overflow:ellipsis;white-space:nowrap}.mini-span-label b{width:48px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis}.mini-span-track{position:relative;height:18px;background:repeating-linear-gradient(90deg,transparent,transparent calc(25% - 1px),rgba(255,255,255,.04) 25%)}.mini-span-track i{position:absolute;top:6px;height:6px;min-width:4px;border-radius:3px;background:var(--agent-color);opacity:.85}.mini-span-track i.tool,.mini-span-track i.retrieval{height:4px;top:7px;background:#6dd6c0}.mini-span-track i.handoff{height:8px;top:5px;background:#b88cff}.mini-span-time{text-align:right;color:#616b7d;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:7px}
.trace-warning { display: flex; gap: 8px; margin-top: 10px; border: 1px solid rgba(245,185,66,.15); border-radius: 10px; padding: 9px 10px; background: rgba(245,185,66,.045); color: #e6c475; }.trace-warning>span { display:grid;width:17px;height:17px;flex-shrink:0;place-items:center;border-radius:50%;background:rgba(245,185,66,.12);font-size:9px;font-weight:800}.trace-warning p{color:var(--text-tertiary);font-size:8px;line-height:1.5}.trace-warning strong{display:block;margin-bottom:2px;color:#e8c875;font-size:9px}
.trust-verified{color:#70e0a3;background:rgba(112,224,163,.1)}.trust-degraded{color:#f5b942;background:rgba(245,185,66,.1)}.trust-partial{color:#aab4c3;background:rgba(148,163,184,.1)}.trust-compromised{color:#f27b7b;background:rgba(239,68,68,.1)}
@media(max-width:800px){.summary-metric:nth-of-type(n+3){display:none}.outcome-row{grid-template-columns:1fr repeat(2,60px)}.token-stat:last-child{display:none}}
</style>
