<script setup lang="ts">
/**
 * AgentTraceBar — 折叠式 Agent handoff 链（吸收 AgentDivider + HandoffTimeline）。
 *
 * 默认折叠：单行 "Knowledge → Review → Brain · natural_end"
 * 点击展开：每个 Agent 的操作摘要 + trace 按钮
 */
import { ref, computed } from "vue";
import { agentMeta, agentColors } from "../shared/design-tokens";

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
  for (const s of props.steps) ids.push(s.to);
  return ids;
});

function verdictLabel(v: string): string {
  switch (v) {
    case 'natural_end': return '自然结束';
    case 'loop_detected': return '检测到循环';
    case 'max_depth_reached': return '已达最大深度';
    case 'missing_handoff': return '可能需要接力';
    default: return v;
  }
}

function verdictColor(v: string): string {
  switch (v) {
    case 'natural_end': return 'var(--color-success)';
    case 'loop_detected':
    case 'max_depth_reached': return 'var(--color-danger)';
    default: return 'var(--color-warning)';
  }
}
</script>

<template>
  <div v-if="steps.length || verdict" class="max-w-content mx-auto w-full px-4">
    <!-- Collapsed bar -->
    <button
      class="w-full flex items-center gap-2 py-1.5 text-[11px] rounded-lg transition-all hover:brightness-110 group"
      :style="{ color: 'var(--text-tertiary)', background: expanded ? 'var(--surface-hover)' : 'transparent' }"
      @click="expanded = !expanded"
    >
      <svg
        class="w-3 h-3 transition-transform shrink-0"
        :class="{ 'rotate-90': expanded }"
        fill="none" stroke="currentColor" viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
      </svg>
      <span class="font-medium" :style="{ color: 'var(--text-secondary)' }">Trace</span>

      <!-- Agent chain -->
      <template v-for="(id, i) in allAgentIds" :key="i">
        <span v-if="i > 0" class="opacity-30">→</span>
        <span
          class="font-medium"
          :style="{ color: `var(--agent-${id})` }"
        >{{ agentMeta[id]?.short || id }}</span>
      </template>

      <!-- Verdict -->
      <span
        v-if="verdict"
        class="ml-auto text-[9px] px-1.5 py-px rounded-full font-medium"
        :style="{
          color: verdictColor(verdict),
          background: verdictColor(verdict) + '12',
        }"
      >{{ verdictLabel(verdict) }}</span>

      <!-- Per-phase trace buttons -->
      <template v-for="step in steps.filter(s => s.traceId)" :key="'t' + step.traceId">
        <button
          class="text-[9px] px-1.5 py-px rounded-full font-mono opacity-0 group-hover:opacity-60 hover:!opacity-100 transition-all border"
          :style="{
            color: `var(--agent-${step.to})`,
            borderColor: `var(--agent-${step.to})` + '30',
          }"
          @click.stop="emit('traceClick', step.traceId!)"
          :title="`${agentMeta[step.to]?.label || step.to} trace`"
        >{{ step.traceId!.slice(0, 6) }}</button>
      </template>
    </button>

    <!-- Expanded detail -->
    <div
      v-if="expanded"
      class="mt-2 mb-4 p-3 rounded-xl border space-y-2"
      :style="{ background: 'var(--surface-base)', borderColor: 'var(--border-subtle)' }"
    >
      <div
        v-for="(step, i) in steps"
        :key="i"
        class="text-[12px] leading-relaxed"
        :style="{ color: 'var(--text-secondary)' }"
      >
        <span :style="{ color: `var(--agent-${step.from})` }">{{ agentMeta[step.from]?.label || step.from }}</span>
        <span class="opacity-50"> → </span>
        <span :style="{ color: `var(--agent-${step.to})` }">@{{ step.to }}</span>
        <template v-if="step.trigger"> — "{{ step.trigger.slice(0, 80) }}{{ step.trigger.length > 80 ? '…' : '' }}"</template>
        <button
          v-if="step.traceId"
          class="ml-2 text-[9px] underline underline-offset-2 opacity-50 hover:opacity-100"
          :style="{ color: `var(--agent-${step.to})` }"
          @click="emit('traceClick', step.traceId!)"
        >trace</button>
      </div>

      <!-- Verdict detail -->
      <div
        v-if="verdict"
        class="text-[11px] pt-1.5 border-t"
        :style="{ borderColor: 'var(--border-subtle)', color: verdictColor(verdict) }"
      >
        {{ verdictReason || verdictLabel(verdict) }}
      </div>
    </div>
  </div>
</template>
