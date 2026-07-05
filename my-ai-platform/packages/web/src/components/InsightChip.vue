<script setup lang="ts">
export interface InsightChipData {
  id: string;
  type: "note_ref" | "saved" | "tool_result" | "review_finding" | "brain_expansion";
  label: string;
  count?: number;
  payload?: unknown;
}

defineProps<{
  chip: InsightChipData;
}>();

defineEmits<{
  click: [chip: InsightChipData];
}>();

function chipStyle(type: string) {
  switch (type) {
    case "note_ref": return { icon: "↗", color: "var(--agent-knowledge)" };
    case "saved": return { icon: "✓", color: "var(--color-success)" };
    case "tool_result": return { icon: "◇", color: "var(--text-tertiary)" };
    case "review_finding": return { icon: "!", color: "var(--agent-review)" };
    case "brain_expansion": return { icon: "✦", color: "var(--agent-brain)" };
    default: return { icon: "•", color: "var(--text-tertiary)" };
  }
}
</script>

<template>
  <button
    class="insight-chip"
    :style="{
      color: chipStyle(chip.type).color,
      background: chipStyle(chip.type).color + '12',
      borderColor: chipStyle(chip.type).color + '26',
    }"
    @click="$emit('click', chip)"
  >
    <span>{{ chipStyle(chip.type).icon }}</span>
    <b>{{ chip.label }}</b>
    <em v-if="chip.count !== undefined">{{ chip.count }}</em>
  </button>
</template>

<style scoped>
.insight-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid;
  border-radius: 999px;
  padding: 7px 10px;
  font-size: 11px;
  transition: 150ms ease;
}

.insight-chip:hover {
  filter: brightness(1.12);
  transform: translateY(-1px);
}

.insight-chip span {
  font-size: 10px;
}

.insight-chip b,
.insight-chip em {
  font-weight: 600;
  font-style: normal;
}

.insight-chip em {
  opacity: 0.65;
}
</style>
