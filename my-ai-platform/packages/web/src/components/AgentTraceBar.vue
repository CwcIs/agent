<script setup lang="ts">
import { ref, computed } from "vue";
import { agentMeta } from "../shared/design-tokens";

interface HandoffStep {
  from: string;
  to: string;
  trigger: string;
  traceId?: string;
}

const props = defineProps<{
  steps: HandoffStep[];
  verdict?: string | null;
  verdictReason?: string | null;
}>();

const emit = defineEmits<{
  traceClick: [traceId: string];
}>();

const expanded = ref(false);

const allAgentIds = computed(() => {
  if (!props.steps.length) return [];
  const ids = [props.steps[0].from];
  for (const step of props.steps) ids.push(step.to);
  return ids;
});

function verdictLabel(value: string): string {
  switch (value) {
    case "natural_end": return "自然结束";
    case "loop_detected": return "检测到循环";
    case "max_depth_reached": return "达到最大深度";
    case "missing_handoff": return "缺少明确接力";
    default: return value;
  }
}

function verdictColor(value: string): string {
  switch (value) {
    case "natural_end": return "var(--color-success)";
    case "loop_detected":
    case "max_depth_reached": return "var(--color-danger)";
    default: return "var(--color-warning)";
  }
}
</script>

<template>
  <div v-if="steps.length || verdict" class="agent-trace-bar">
    <button class="trace-summary" :class="{ expanded }" @click="expanded = !expanded">
      <svg class="chevron" :class="{ expanded }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
      </svg>
      <span class="trace-title">Handoff Trace</span>

      <template v-for="(id, index) in allAgentIds" :key="`${id}-${index}`">
        <span v-if="index > 0" class="arrow">→</span>
        <span class="agent-short" :style="{ color: `var(--agent-${id})` }">
          {{ agentMeta[id]?.short || id }}
        </span>
      </template>

      <span
        v-if="verdict"
        class="verdict"
        :style="{ color: verdictColor(verdict), background: verdictColor(verdict) + '12' }"
      >
        {{ verdictLabel(verdict) }}
      </span>

      <button
        v-for="step in steps.filter(s => s.traceId)"
        :key="step.traceId"
        class="phase-trace-btn"
        :style="{ color: `var(--agent-${step.to})`, borderColor: `var(--agent-${step.to})` + '30' }"
        :title="`${agentMeta[step.to]?.label || step.to} trace`"
        @click.stop="emit('traceClick', step.traceId!)"
      >
        {{ step.traceId!.slice(0, 6) }}
      </button>
    </button>

    <div v-if="expanded" class="trace-detail">
      <div v-if="!steps.length" class="trace-empty">
        单 Agent 回答没有 handoff；下方的 Trace Summary 展示本次 LLM 调用成本与耗时。
      </div>
      <div v-for="(step, index) in steps" :key="index" class="trace-step">
        <span :style="{ color: `var(--agent-${step.from})` }">{{ agentMeta[step.from]?.label || step.from }}</span>
        <span class="arrow">→</span>
        <span :style="{ color: `var(--agent-${step.to})` }">@{{ step.to }}</span>
        <template v-if="step.trigger">
          <span class="trigger">“{{ step.trigger.slice(0, 80) }}{{ step.trigger.length > 80 ? '…' : '' }}”</span>
        </template>
        <button v-if="step.traceId" class="trace-link" @click="emit('traceClick', step.traceId!)">
          查看 trace
        </button>
      </div>

      <div v-if="verdict" class="verdict-detail" :style="{ color: verdictColor(verdict) }">
        {{ verdictReason || verdictLabel(verdict) }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-trace-bar {
  width: min(760px, calc(100% - 32px));
  margin: 0 auto 10px;
}

.trace-summary {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid transparent;
  border-radius: 14px;
  color: var(--text-tertiary);
  padding: 8px 10px;
  font-size: 11px;
  transition: 150ms ease;
}

.trace-summary:hover,
.trace-summary.expanded {
  background: rgba(255,255,255,0.045);
  border-color: var(--border-subtle);
}

.chevron {
  width: 13px;
  height: 13px;
  transition: transform 150ms ease;
}

.chevron.expanded {
  transform: rotate(90deg);
}

.trace-title {
  color: var(--text-secondary);
  font-weight: 650;
}

.arrow {
  opacity: 0.35;
}

.agent-short {
  font-weight: 750;
}

.verdict {
  margin-left: auto;
  border-radius: 999px;
  padding: 3px 7px;
  font-size: 10px;
  font-weight: 650;
}

.phase-trace-btn {
  border: 1px solid;
  border-radius: 999px;
  padding: 3px 7px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  opacity: 0.68;
  transition: 150ms ease;
}

.phase-trace-btn:hover {
  opacity: 1;
  background: rgba(255,255,255,0.04);
}

.trace-detail {
  margin-top: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  background: rgba(255,255,255,0.035);
  padding: 12px;
}

.trace-empty,
.trace-step {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.trace-step {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}

.trigger {
  color: var(--text-tertiary);
}

.trace-link {
  color: var(--brand);
  text-decoration: underline;
  text-underline-offset: 3px;
  font-size: 11px;
}

.verdict-detail {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
  font-size: 11px;
}
</style>
