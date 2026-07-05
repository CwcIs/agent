<script setup lang="ts">
import { ref } from "vue";

interface Toast {
  id: number;
  message: string;
  type: "info" | "success" | "error";
}

const toasts = ref<Toast[]>([]);
let nextId = 0;

function show(message: string, type: "info" | "success" | "error" = "info") {
  const id = nextId++;
  toasts.value.push({ id, message, type });
  setTimeout(() => {
    toasts.value = toasts.value.filter((t) => t.id !== id);
  }, 3000);
}

function remove(id: number) {
  toasts.value = toasts.value.filter((t) => t.id !== id);
}

defineExpose({ show });
</script>

<template>
  <Teleport to="body">
    <div class="fixed bottom-20 right-4 z-[100] flex flex-col gap-1.5 pointer-events-none">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="pointer-events-auto px-3 py-2 rounded-lg text-[11px] flex items-center gap-2 shadow-xl transition-all animate-fade-in border"
        :style="{
          background: toast.type === 'success'
            ? 'rgba(112,224,163,0.08)'
            : toast.type === 'error'
              ? 'rgba(255,107,107,0.08)'
              : 'rgba(255,255,255,0.05)',
          borderColor: toast.type === 'success'
            ? 'rgba(112,224,163,0.15)'
            : toast.type === 'error'
              ? 'rgba(255,107,107,0.15)'
              : 'rgba(255,255,255,0.08)',
          color: toast.type === 'success'
            ? '#70E0A3'
            : toast.type === 'error'
              ? '#FF6B6B'
              : '#9AA4B2',
        }"
      >
        <svg
          v-if="toast.type === 'success'"
          class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
        <svg
          v-else-if="toast.type === 'error'"
          class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
        <span>{{ toast.message }}</span>
        <button class="ml-2 opacity-50 hover:opacity-100" @click="remove(toast.id)">
          <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  </Teleport>
</template>
