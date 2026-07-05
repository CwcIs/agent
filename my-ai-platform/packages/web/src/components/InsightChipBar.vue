<script setup lang="ts">
import InsightChip from "./InsightChip.vue";
import type { InsightChipData } from "./InsightChip.vue";

defineProps<{
  chips: InsightChipData[];
}>();

defineEmits<{
  chipClick: [chip: InsightChipData];
}>();
</script>

<template>
  <div class="flex items-center gap-2 flex-wrap">
    <InsightChip
      v-for="chip in chips"
      :key="chip.id"
      :chip="chip"
      @click="$emit('chipClick', chip)"
    />
  </div>
</template>
