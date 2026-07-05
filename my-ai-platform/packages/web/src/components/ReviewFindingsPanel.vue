<script setup lang="ts">
defineProps<{
  payload?: unknown;
}>();
</script>

<template>
  <div class="space-y-3">
    <p class="text-[13px]" :style="{ color: 'var(--text-secondary)' }">
      Review Agent 的发现将在这里展示。
    </p>
    <p class="text-[11px]" :style="{ color: 'var(--text-tertiary)' }">
      包括：隐含假设、逻辑漏洞、潜在风险。
    </p>
  </div>
</template>
