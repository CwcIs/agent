<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  agentId: string;
  label: string;
  verb?: string;
  verdict?: string | null;
  verdictWarning?: string | null;
}>();

const AGENT_HEX: Record<string, string> = {
  knowledge: "#6EA8FF",
  review: "#FFB86C",
  brain: "#B892FF",
};

const AGENT_BG: Record<string, string> = {
  knowledge: "rgba(110,168,255,0.10)",
  review: "rgba(255,184,108,0.10)",
  brain: "rgba(184,146,255,0.10)",
};

const AGENT_ROLE: Record<string, string> = {
  knowledge: "正在整理相关记忆",
  review: "正在检查隐含假设",
  brain: "正在扩展相邻想法",
};

const AGENT_ICON: Record<string, string> = {
  knowledge: "K",
  review: "R",
  brain: "B",
};

const agentColor = computed(() => AGENT_HEX[props.agentId] || "#A9A29A");
const agentBg = computed(() => AGENT_BG[props.agentId] || "rgba(255,255,255,0.06)");
const agentRole = computed(() => props.verb || AGENT_ROLE[props.agentId] || "正在处理");
const agentIcon = computed(() => AGENT_ICON[props.agentId] || "?");

const verdictLabel = computed(() => {
  if (!props.verdict) return null;
  switch (props.verdict) {
    case "natural_end": return "自然结束";
    case "missing_handoff": return "可能需要接力，但没有明确 @agent";
    case "loop_detected": return "检测到循环，已停止调度";
    case "max_depth_reached": return "达到最大调度深度";
    default: return props.verdict;
  }
});
</script>

<template>
  <div class="agent-divider">
    <div class="divider-line" />
    <div class="agent-badge" :style="{ background: agentBg, borderColor: agentColor + '33', color: agentColor }">
      <span :style="{ background: agentColor + '22' }">{{ agentIcon }}</span>
      <b>{{ label }}</b>
      <em>{{ agentRole }}</em>
    </div>
    <div class="divider-line right" />
  </div>

  <div v-if="verdict" class="verdict-pill" :class="verdict">
    {{ verdictLabel }}
    <template v-if="verdictWarning"> · {{ verdictWarning }}</template>
  </div>
</template>

<style scoped>
.agent-divider {
  width: min(760px, calc(100% - 32px));
  margin: 14px auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

.divider-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(to right, transparent, var(--border-subtle));
}

.divider-line.right {
  background: linear-gradient(to left, transparent, var(--border-subtle));
}

.agent-badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid;
  border-radius: 999px;
  padding: 7px 11px;
  font-size: 11px;
  white-space: nowrap;
}

.agent-badge span {
  width: 18px;
  height: 18px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  font-size: 9px;
  font-weight: 800;
}

.agent-badge b {
  font-weight: 700;
}

.agent-badge em {
  color: var(--text-secondary);
  font-style: normal;
}

.verdict-pill {
  width: fit-content;
  max-width: calc(100% - 32px);
  margin: -4px auto 12px;
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 11px;
}

.verdict-pill.natural_end {
  color: var(--color-success);
  background: rgba(112,224,163,0.08);
}

.verdict-pill.missing_handoff,
.verdict-pill.max_depth_reached {
  color: var(--color-warning);
  background: rgba(255,209,102,0.08);
}

.verdict-pill.loop_detected {
  color: var(--color-danger);
  background: rgba(255,107,107,0.08);
}
</style>
