<script setup lang="ts">
/**
 * RelatedNotesPanel — Drawer 内容：相关笔记列表
 */
defineProps<{
  payload?: unknown;
}>();

defineEmits<{
  followUp: [query: string];
}>();
</script>

<template>
  <div class="space-y-3">
    <p class="text-[13px]" :style="{ color: 'var(--text-secondary)' }">
      相关内容将在这里显示。
    </p>
    <p class="text-[11px]" :style="{ color: 'var(--text-tertiary)' }">
      当 AI 搜索到相关笔记时，点击 Insight Chip 即可查看。
    </p>
  </div>
</template>
