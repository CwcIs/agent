<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  streaming: boolean;
  runningAgents: string[];
  sessionId: string;
  dailyNoteCount?: number;
  dailyTrendCount?: number;
  dailyAnomalyCount?: number;
  smartBadges?: Array<{ type: string; label: string; priority: string }>;
}>();

const emit = defineEmits<{
  toggleDigest: [];
}>();

const hasDigestHighlights = computed(() =>
  (props.dailyTrendCount ?? 0) > 0 || (props.dailyAnomalyCount ?? 0) > 0 ||
  (props.smartBadges?.length ?? 0) > 0
);
</script>

<template>
  <header class="top-status-bar">
    <slot name="toggle" />

    <div class="top-title">
      <span class="eyebrow">AI Thought Studio</span>
      <strong>Inbox</strong>
    </div>

    <div class="flex-1" />

    <button
      v-if="dailyNoteCount || smartBadges?.length"
      class="daily-badge"
      :class="{ active: hasDigestHighlights }"
      @click="emit('toggleDigest')"
    >
      <template v-if="dailyNoteCount">Today · {{ dailyNoteCount }} notes</template>
      <template v-if="dailyTrendCount"> · {{ dailyTrendCount }} themes</template>
      <template v-for="b in smartBadges?.filter(b => b.priority === 'high')" :key="b.type">
        · {{ b.label }}
      </template>
    </button>

    <span class="status-dot" :class="{ streaming }" />
    <span class="cmd-hint">⌘K</span>
  </header>
</template>

<style scoped>
.top-status-bar {
  height: 58px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 22px;
  border-bottom: 1px solid var(--border-subtle);
  background: rgba(13,14,20,0.72);
  backdrop-filter: blur(22px);
  flex-shrink: 0;
}

.top-title {
  display: grid;
  gap: 1px;
}

.eyebrow {
  color: var(--text-tertiary);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.top-title strong {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 650;
}

.daily-badge,
.cmd-hint {
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: rgba(255,255,255,0.04);
  color: var(--text-tertiary);
  padding: 7px 10px;
  font-size: 11px;
}

.daily-badge.active {
  background: var(--brand-soft);
  border-color: var(--brand-border);
  color: var(--brand);
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--color-success);
  box-shadow: 0 0 16px rgba(112,224,163,0.45);
}

.status-dot.streaming {
  background: var(--agent-knowledge);
  box-shadow: 0 0 16px rgba(110,168,255,0.55);
}

.cmd-hint {
  display: none;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

@media (min-width: 1024px) {
  .cmd-hint { display: inline-block; }
}
</style>
