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
</script>

<template>
  <header
    class="flex items-center gap-3 px-4 h-11 border-b shrink-0"
    :style="{ borderColor: 'var(--border-subtle)', background: 'var(--surface-base)' }"
  >
    <slot name="toggle" />

    <!-- Brand -->
    <span class="text-[11px] font-semibold tracking-[0.04em]" :style="{ color: 'var(--text-secondary)' }">
      Thought Studio
    </span>

    <div class="flex-1" />

    <!-- Daily Digest Badge -->
    <button
      v-if="dailyNoteCount"
      class="flex items-center gap-1.5 text-[10px] px-2 py-1 rounded-full transition-all hover:brightness-110 shrink-0 border"
      :style="{
        background: hasDigestHighlights ? 'var(--brand-soft)' : 'rgba(255,255,255,0.02)',
        borderColor: hasDigestHighlights ? 'var(--brand-border)' : 'var(--border-subtle)',
        color: hasDigestHighlights ? 'var(--brand)' : 'var(--text-tertiary)',
      }"
      @click="emit('toggleDigest')"
    >
      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
      Today {{ dailyNoteCount }} notes
      <template v-if="dailyTrendCount"> · {{ dailyTrendCount }} trends</template>
    </button>

    <!-- Status dot -->
    <span
      class="w-1.5 h-1.5 rounded-full shrink-0"
      :class="streaming ? 'animate-pulse-glow' : ''"
      :style="{ background: streaming ? 'var(--agent-knowledge)' : 'var(--color-success)' }"
    />

    <!-- Cmd+K hint -->
    <span
      class="text-[9px] font-mono px-1.5 py-0.5 rounded hidden lg:block"
      :style="{ background: 'rgba(255,255,255,0.03)', color: 'var(--text-tertiary)', opacity: 0.5 }"
    >⌘K</span>
  </header>
</template>
