<script setup lang="ts">
defineProps<{
  payload?: unknown;
}>();
</script>

<template>
  <div class="space-y-3">
    <p class="text-[13px]" :style="{ color: 'var(--text-secondary)' }">
      Brain Agent 的联想将在这里展示。
    </p>
    <p class="text-[11px]" :style="{ color: 'var(--text-tertiary)' }">
      包括：跨界连接、类比、新方向建议。
    </p>
  </div>
</template>
