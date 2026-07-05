<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  streaming: boolean;
  runningAgents: string[];
  sessionId: string;
  dailyNoteCount?: number;
  dailyTrendCount?: number;
  dailyAnomalyCount?: number;
}>();

const emit = defineEmits<{
  toggleDigest: [];
}>();

const hasDigestHighlights = computed(() =>
  (props.dailyTrendCount ?? 0) > 0 || (props.dailyAnomalyCount ?? 0) > 0
);

const statusText = computed(() => {
  if (props.streaming && props.runningAgents.length) {
    return props.runningAgents.join(" · ");
  }
  if (props.streaming) return "思考中…";
  return "就绪";
});
</script>

<template>
  <header class="flex items-center gap-3 px-4 h-11 border-b shrink-0"
    style="border-color: var(--border-subtle); background: var(--bg-panel)"
  >
    <!-- 侧栏切换 -->
    <slot name="toggle" />

    <!-- 品牌 -->
    <span class="text-xs font-semibold tracking-wide" style="color: var(--text-muted)">
      Thought Cockpit
    </span>

    <!-- Session 状态 -->
    <span class="text-[9px] font-mono px-1.5 py-0.5 rounded"
      style="background: 'rgba(255,255,255,0.03)'; color: 'var(--text-muted)'"
    >
      {{ sessionId.slice(0, 8) }}
    </span>

    <div class="flex-1" />

    <!-- Agent 状态指示 -->
    <div class="flex items-center gap-1.5">
      <span
        class="w-1.5 h-1.5 rounded-full"
        :class="streaming ? 'animate-pulse-glow' : ''"
        :style="{ background: streaming ? 'var(--agent-knowledge)' : 'var(--text-muted)' }"
      />
      <span class="text-[10px]" style="color: var(--text-muted)">{{ statusText }}</span>
    </div>

    <!-- Daily Digest Badge -->
    <button
      v-if="dailyNoteCount"
      class="flex items-center gap-1.5 text-[10px] px-2 py-1 rounded-full transition-colors shrink-0"
      :style="{
        background: hasDigestHighlights ? 'rgba(124,156,255,0.08)' : 'rgba(255,255,255,0.03)',
        border: hasDigestHighlights ? '1px solid rgba(124,156,255,0.15)' : '1px solid rgba(255,255,255,0.04)',
        color: hasDigestHighlights ? 'var(--agent-knowledge)' : 'var(--text-muted)',
      }"
      @click="emit('toggleDigest')"
    >
      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
      Today: {{ dailyNoteCount }} notes
      <template v-if="dailyTrendCount"> · {{ dailyTrendCount }} trends</template>
      <template v-if="dailyAnomalyCount"> · {{ dailyAnomalyCount }} anomaly</template>
    </button>

    <!-- 快捷键提示 -->
    <span class="text-[9px] font-mono px-1.5 py-0.5 rounded hidden lg:block"
      style="background: 'rgba(255,255,255,0.02)'; color: 'var(--text-muted)'; opacity: 0.5"
    >Ctrl+/ 输入</span>
  </header>
</template>
