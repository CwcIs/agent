<script setup lang="ts">
/**
 * InsightChip — 单个可点击 chip。
 *
 * 类型：
 * - note_ref: "引用 4 条笔记"
 * - saved: "已保存"
 * - tool_result: "search_notes 完成"
 * - review_finding: "Review 发现 2 个假设"
 * - brain_expansion: "Brain 联想 3 个方向"
 */

export interface InsightChipData {
  id: string;
  type: 'note_ref' | 'saved' | 'tool_result' | 'review_finding' | 'brain_expansion';
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
    case 'note_ref':        return { icon: '▦', color: 'var(--agent-knowledge)' };
    case 'saved':           return { icon: '✓', color: 'var(--color-success)' };
    case 'tool_result':     return { icon: '⚙', color: 'var(--text-tertiary)' };
    case 'review_finding':  return { icon: '⚠', color: 'var(--agent-review)' };
    case 'brain_expansion': return { icon: '◇', color: 'var(--agent-brain)' };
    default:                return { icon: '•', color: 'var(--text-tertiary)' };
  }
}
</script>

<template>
  <button
    class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all hover:brightness-110 border"
    :style="{
      color: chipStyle(chip.type).color,
      background: chipStyle(chip.type).color + '10',
      borderColor: chipStyle(chip.type).color + '20',
    }"
    @click="$emit('click', chip)"
  >
    <span class="text-[9px]">{{ chipStyle(chip.type).icon }}</span>
    <span>{{ chip.label }}</span>
    <span
      v-if="chip.count !== undefined"
      class="text-[9px] opacity-60 ml-0.5"
    >{{ chip.count }}</span>
  </button>
</template>
