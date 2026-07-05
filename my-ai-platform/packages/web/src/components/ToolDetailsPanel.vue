<script setup lang="ts">
defineProps<{
  payload?: unknown;
}>();
</script>

<template>
  <div class="space-y-3">
    <p class="text-[13px]" :style="{ color: 'var(--text-secondary)' }">
      工具调用详情将在这里展示。
    </p>
    <p class="text-[11px]" :style="{ color: 'var(--text-tertiary)' }">
      包括：输入参数、返回结果、耗时。
    </p>
  </div>
</template>
