<script setup lang="ts">
import { ref, onUnmounted } from "vue";

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
        class="pointer-events-auto px-3 py-2 rounded-lg text-[11px] flex items-center gap-2 shadow-xl backdrop-blur-sm transition-all animate-fade-in"
        :class="[
          toast.type === 'success'
            ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
            : toast.type === 'error'
              ? 'bg-red-500/10 border border-red-500/20 text-red-400'
              : 'bg-white/[0.06] border border-white/[0.08] text-gray-300'
        ]"
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
        <button class="ml-2 text-gray-600 hover:text-gray-400" @click="remove(toast.id)">
          <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.animate-fade-in {
  animation: fadeIn 0.2s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
