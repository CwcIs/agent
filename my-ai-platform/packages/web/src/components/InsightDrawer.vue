<script setup lang="ts">
import { layout, easing, durations, shadows } from "../shared/design-tokens";

defineProps<{
  open: boolean;
}>();

const emit = defineEmits<{
  close: [];
}>();
</script>

<template>
  <Transition name="drawer">
    <aside
      v-if="open"
      class="shrink-0 border-l overflow-y-auto relative"
      :style="{
        width: layout.drawerWidth,
        background: 'var(--surface-base)',
        borderColor: 'var(--border-subtle)',
        boxShadow: shadows.panel,
      }"
    >
      <!-- Header -->
      <div
        class="flex items-center justify-between px-4 h-11 shrink-0 border-b sticky top-0 z-10"
        :style="{ borderColor: 'var(--border-subtle)', background: 'var(--surface-base)' }"
      >
        <span class="text-[11px] font-semibold tracking-[0.08em]" :style="{ color: 'var(--text-secondary)' }">
          <slot name="title">Insight</slot>
        </span>
        <button
          class="p-1 rounded hover:brightness-125 transition-all opacity-40 hover:opacity-70"
          :style="{ color: 'var(--text-secondary)' }"
          @click="emit('close')"
          title="关闭 (Esc)"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Content -->
      <div class="p-4">
        <slot />
      </div>
    </aside>
  </Transition>
</template>
