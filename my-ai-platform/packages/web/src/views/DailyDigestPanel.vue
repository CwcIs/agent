<script setup lang="ts">
import { ref, onMounted } from "vue";

interface Digest {
  date: string;
  noteCount: number;
  narrative: string;
  followUps: string[];
  citedNotes: Array<{ noteId: string; title: string }>;
}

const emit = defineEmits<{ followUp: [q: string] }>();

const digest = ref<Digest | null>(null);
const loading = ref(true);
const collapsed = ref(false);

onMounted(async () => {
  try {
    const resp = await fetch("/digest");
    digest.value = await resp.json();
  } catch {
    digest.value = null;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <!-- 加载中 -->
  <div v-if="loading" class="px-5 py-3 border-b border-white/[0.06] flex items-center gap-2 shrink-0">
    <div class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
    <span class="text-xs text-gray-600">生成今日回顾...</span>
  </div>

  <!-- 有数据 -->
  <div v-else-if="digest" class="border-b border-white/[0.06] shrink-0">
    <button
      class="w-full flex items-center gap-2.5 px-5 py-2.5 hover:bg-white/[0.02] transition-colors text-left"
      @click="collapsed = !collapsed"
    >
      <div class="w-1.5 h-1.5 rounded-full bg-indigo-500/60 shrink-0" />
      <span class="text-xs text-gray-500 font-medium">{{ digest.date }} 回顾</span>
      <span class="text-xs text-gray-700 ml-1">{{ digest.noteCount }} 条笔记</span>
      <svg
        class="w-3 h-3 text-gray-700 ml-auto transition-transform"
        :class="collapsed ? '' : 'rotate-180'"
        fill="none" stroke="currentColor" viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
      </svg>
    </button>

    <div v-if="!collapsed" class="px-5 pb-3">
      <p class="text-xs text-gray-400 leading-relaxed">{{ digest.narrative }}</p>
      <div v-if="digest.followUps?.length" class="mt-2.5 flex flex-wrap gap-1.5">
        <button
          v-for="(q, i) in digest.followUps"
          :key="i"
          class="text-[11px] px-2.5 py-1 rounded-full border border-indigo-500/30 text-indigo-400 hover:bg-indigo-500/10 transition-colors"
          @click="emit('followUp', q)"
        >
          {{ q }}
        </button>
      </div>
    </div>
  </div>
</template>
