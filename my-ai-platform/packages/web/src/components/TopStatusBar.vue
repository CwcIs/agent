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

const emit = defineEmits<{ toggleDigest: [] }>();

const digestLabel = computed(() => {
  const notes = props.dailyNoteCount ?? 0;
  const themes = props.dailyTrendCount ?? 0;
  if (!notes) return "No notes today";
  return `${notes} notes · ${themes} themes`;
});

const hasHighlights = computed(() =>
  (props.dailyTrendCount ?? 0) > 0 || (props.dailyAnomalyCount ?? 0) > 0 || (props.smartBadges?.length ?? 0) > 0
);
</script>

<template>
  <header class="topbar">
    <slot name="toggle" />
    <div class="title-block">
      <span>Studio</span>
      <strong>Thinking Inbox</strong>
    </div>

    <div class="status-strip">
      <span class="live-dot" :class="{ streaming }" />
      <span>{{ streaming ? 'Agents working' : 'Connected' }}</span>
    </div>

    <div class="topbar-spacer" />

    <button class="digest-button" :class="{ active: hasHighlights }" @click="emit('toggleDigest')">
      <span>Daily Review</span>
      <strong>{{ digestLabel }}</strong>
    </button>
    <kbd class="cmd-key">⌘K</kbd>
  </header>
</template>

<style scoped>
.topbar {
  height: 72px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 0 28px;
  border-bottom: 1px solid var(--border-subtle);
  background: rgba(11, 12, 18, 0.58);
  backdrop-filter: blur(24px);
}
.title-block { display: grid; gap: 2px; }
.title-block span { color: var(--text-tertiary); font-size: 10px; font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase; }
.title-block strong { color: var(--text-primary); font-size: 17px; letter-spacing: -0.035em; }
.status-strip { display: flex; align-items: center; gap: 8px; border: 1px solid var(--border-subtle); border-radius: 999px; padding: 7px 10px; color: var(--text-secondary); font-size: 11px; background: rgba(255,255,255,0.035); }
.live-dot { width: 7px; height: 7px; border-radius: 999px; background: var(--color-success); box-shadow: 0 0 18px rgba(119,228,173,.48); }
.live-dot.streaming { background: var(--agent-knowledge); box-shadow: 0 0 18px rgba(121,174,255,.56); }
.topbar-spacer { flex: 1; }
.digest-button { min-width: 160px; display: grid; gap: 1px; text-align: left; border: 1px solid var(--border-subtle); border-radius: 16px; padding: 9px 12px; color: var(--text-secondary); background: rgba(255,255,255,0.04); transition: 160ms ease; }
.digest-button:hover, .digest-button.active { border-color: var(--brand-border); background: var(--brand-soft); }
.digest-button span { color: var(--text-tertiary); font-size: 10px; }
.digest-button strong { color: var(--text-primary); font-size: 12px; }
.cmd-key { border: 1px solid var(--border-subtle); border-radius: 11px; padding: 7px 9px; color: var(--text-tertiary); background: rgba(255,255,255,0.035); font-size: 11px; }
@media (max-width: 820px) { .status-strip, .digest-button { display: none; } .topbar { padding: 0 16px; } }
</style>
