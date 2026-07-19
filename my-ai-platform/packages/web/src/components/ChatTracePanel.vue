<script setup lang="ts">
import {
  AGENT_TRACE_BG,
  AGENT_TRACE_COLOR,
  formatCost,
  formatMs,
} from "../chat/model";
import type { TraceData } from "../composables/useChatTrace";
import { trustLabel } from "../trace/model";

function trustClass(status: string): string {
  if (status === "verified") return "ok";
  if (status === "compromised") return "bad";
  return "warn";
}

defineProps<{
  traceId: string;
  phaseTraceLabel: string | null;
  traceData: TraceData | null;
  traceLoading: boolean;
  traceExpanded: boolean;
}>();

defineEmits<{
  toggle: [];
  reset: [];
}>();
</script>

<template>
  <div class="trace-summary-panel">
    <div v-if="phaseTraceLabel" class="phase-row">
      <span>Viewing phase</span>
      <code>{{ phaseTraceLabel }}</code>
      <button @click.stop="$emit('reset')">Back to default trace</button>
    </div>

    <div class="trace-card" @click="$emit('toggle')">
      <div class="trace-card-head">
        <span class="trace-card-title">Trace Summary</span>
        <code>{{ traceId.slice(0, 8) }}</code>

        <template v-if="traceData">
          <span class="dot-sep">·</span>
          <span :class="trustClass(traceData.trust.status)">
            {{ trustLabel(traceData.trust.status) }} {{ traceData.trust.score }}
          </span>
          <span class="dot-sep">·</span>
          <span>{{ traceData.events.length }} events</span>
          <span class="dot-sep">·</span>
          <span>{{ formatCost(traceData.summary.total_cost_usd) }}</span>
          <span class="dot-sep">·</span>
          <span>{{ formatMs(traceData.summary.total_latency_ms) }}</span>
        </template>
        <template v-else>
          <span class="dot-sep">·</span>
          <span>{{ traceLoading ? "loading trace..." : "click to load" }}</span>
        </template>

        <svg class="trace-chevron" :class="{ open: traceExpanded }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
      </div>

      <div v-if="traceExpanded && traceData" class="trace-detail-panel">
        <div v-if="traceData.trust.status !== 'verified'" class="trace-empty">
          {{ traceData.trust.claim }}
          <span v-if="traceData.trust.missing_required_events.length">
            · 缺少 {{ traceData.trust.missing_required_events.join(", ") }}
          </span>
        </div>

        <div v-for="agent in traceData.agents" :key="agent.agent_id" class="trace-agent-group">
          <div class="trace-agent-row">
            <span class="trace-agent-badge" :style="{ background: AGENT_TRACE_BG[agent.agent_id] || 'rgba(255,255,255,0.06)', color: AGENT_TRACE_COLOR[agent.agent_id] || '#9AA4B2' }">
              {{ agent.agent_id }}
            </span>
            <span>{{ agent.call_count }} LLM</span>
            <span>{{ agent.phase_trace_ids.length }} phases</span>
          </div>
        </div>

        <div class="trace-agent-row trace-totals">
          <span>{{ traceData.summary.call_count }} LLM</span>
          <span>{{ traceData.summary.tool_count }} tools</span>
          <span>{{ traceData.summary.retrieval_count }} retrievals</span>
          <span>{{ traceData.trust.verified_citation_count }} verified citations</span>
          <span class="trace-agent-latency">{{ traceData.summary.total_tokens.toLocaleString() }} tokens</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.trace-summary-panel {
  width: min(760px, calc(100% - 32px));
  margin: 0 auto 12px;
  flex-shrink: 0;
}

.phase-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 7px;
  color: var(--text-tertiary);
  font-size: 11px;
}

.phase-row code,
.trace-card code {
  border-radius: 7px;
  background: rgba(255,255,255,0.06);
  color: var(--text-secondary);
  padding: 2px 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
}

.phase-row button {
  margin-left: auto;
  color: var(--brand);
  font-size: 11px;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.trace-card {
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  background: rgba(255,255,255,0.04);
  overflow: hidden;
  cursor: pointer;
}

.trace-card-head,
.trace-agent-row,
.trace-call-row {
  display: flex;
  align-items: center;
}

.trace-card-head {
  gap: 8px;
  padding: 10px 12px;
  color: var(--text-secondary);
  font-size: 11px;
}

.trace-card-title {
  color: var(--text-primary);
  font-weight: 700;
}

.dot-sep {
  color: var(--text-tertiary);
  opacity: 0.55;
}

.trace-chevron {
  width: 13px;
  height: 13px;
  margin-left: auto;
  color: var(--text-tertiary);
  transition: transform 150ms ease;
}

.trace-chevron.open {
  transform: rotate(180deg);
}

.trace-detail-panel {
  border-top: 1px solid var(--border-subtle);
  padding: 10px 12px 12px;
}

.trace-empty {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.trace-agent-group + .trace-agent-group {
  margin-top: 10px;
}

.trace-agent-row,
.trace-call-row {
  gap: 9px;
  color: var(--text-secondary);
  font-size: 11px;
}

.trace-agent-row {
  padding: 5px 0;
}

.trace-call-row {
  padding: 4px 0 4px 30px;
  color: var(--text-tertiary);
}

.trace-agent-badge {
  border-radius: 7px;
  padding: 3px 7px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  font-weight: 700;
}

.trace-agent-latency {
  margin-left: auto;
}

.model {
  color: var(--text-secondary);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.trace-totals {
  margin-top: 10px;
  border-top: 1px solid var(--border-subtle);
  padding-top: 10px;
}

.ok { color: var(--color-success); }
.warn { color: #f5b942; }
.bad { color: var(--color-danger); }
</style>
