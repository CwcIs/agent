<script setup lang="ts">
import { computed } from "vue";
import { agentMeta } from "../shared/design-tokens";

const props = defineProps<{
  streaming: boolean;
  runningAgents: string[];
  sessionId: string;
  threadTitle: string;
  dailyNoteCount?: number;
  dailyTrendCount?: number;
  dailyAnomalyCount?: number;
  smartBadges?: Array<{ type: string; label: string; priority: string }>;
}>();

const emit = defineEmits<{ toggleDigest: []; openHub: [] }>();

const digestLabel = computed(() => {
  const notes = props.dailyNoteCount ?? 0;
  const themes = props.dailyTrendCount ?? 0;
  if (!notes) return "今日无新增";
  return `${notes} notes · ${themes} themes`;
});

const hasHighlights = computed(() =>
  (props.dailyTrendCount ?? 0) > 0 ||
  (props.dailyAnomalyCount ?? 0) > 0 ||
  (props.smartBadges?.length ?? 0) > 0
);
</script>

<template>
  <header class="topbar">
    <slot name="toggle" />
    <div class="thread-heading">
      <span>Active task</span>
      <strong>{{ threadTitle }}</strong>
    </div>

    <div class="agent-roster" aria-label="Agent roster">
      <span v-for="(agent, id) in agentMeta" :key="id" class="agent-state" :class="id" :title="`${agent.label}: ${agent.role}`">
        <i>{{ agent.short }}</i>
        <b>@{{ id }}</b>
      </span>
    </div>

    <div class="topbar-spacer" />

    <div class="connection-state">
      <span class="live-dot" :class="{ streaming }" />
      <span>{{ streaming ? "Agents working" : "Ready" }}</span>
    </div>
    <button class="digest-button" :class="{ active: hasHighlights }" @click="emit('toggleDigest')">
      <span>Daily Review</span>
      <strong>{{ digestLabel }}</strong>
    </button>
    <button class="hub-button" title="打开 Workbench Hub" @click="emit('openHub')">
      <span class="hub-icon">H</span>
      <span>Hub</span>
    </button>
  </header>
</template>

<style scoped>
.topbar {
  height: 62px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 0 18px;
  border-bottom: 1px solid var(--border-subtle);
  background: #0d1115;
}
.thread-heading { min-width: 0; max-width: 260px; display: grid; gap: 2px; }
.thread-heading span { color: var(--text-tertiary); font-size: 9px; font-weight: 750; text-transform: uppercase; }
.thread-heading strong { overflow: hidden; color: var(--text-primary); font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.agent-roster { display: flex; align-items: center; border-left: 1px solid var(--border-subtle); padding-left: 12px; }
.agent-state {
  height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 8px 0 4px;
  border-right: 1px solid var(--border-subtle);
  color: var(--text-tertiary);
  font-size: 9px;
}
.agent-state i {
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 5px;
  background: #1a2229;
  font-style: normal;
  font-weight: 800;
}
.agent-state b { font-weight: 600; }
.agent-state.knowledge i { color: var(--agent-knowledge); }
.agent-state.review i { color: var(--agent-review); }
.agent-state.brain i { color: var(--agent-brain); }
.topbar-spacer { flex: 1; }
.connection-state { display: flex; align-items: center; gap: 7px; color: var(--text-tertiary); font-size: 10px; }
.live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--color-success); }
.live-dot.streaming { background: var(--color-warning); animation: pulse-glow 1.4s ease-in-out infinite; }
.digest-button {
  min-width: 134px;
  display: grid;
  gap: 1px;
  padding: 6px 9px;
  border-left: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  text-align: left;
}
.digest-button:hover strong, .digest-button.active strong { color: #a8dce6; }
.digest-button span { color: var(--text-tertiary); font-size: 9px; }
.digest-button strong { color: var(--text-secondary); font-size: 10px; }
.hub-button {
  height: 34px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 10px 0 5px;
  border: 1px solid #31515c;
  border-radius: 6px;
  background: #16242a;
  color: #d9eef2;
  font-size: 11px;
  font-weight: 700;
}
.hub-button:hover { background: #1b3038; border-color: #49717f; }
.hub-icon { width: 22px; height: 22px; display: grid; place-items: center; border-radius: 4px; background: #223941; color: #a8dce6; font-size: 9px; }
@media (max-width: 900px) {
  .agent-state b, .digest-button { display: none; }
  .agent-state { padding-right: 4px; }
}
@media (max-width: 620px) {
  .agent-roster, .connection-state { display: none; }
  .topbar { padding: 0 10px; }
}
</style>
