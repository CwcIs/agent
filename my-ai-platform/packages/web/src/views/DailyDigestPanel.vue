<script setup lang="ts">
import { ref, computed, onMounted } from "vue";

interface Digest {
  date: string;
  noteCount: number;
  narrative: string;
  followUps: string[];
  citedNotes: Array<{ noteId: string; title: string }>;
  trends: string[];
  anomalies: string[];
}

const emit = defineEmits<{ followUp: [q: string] }>();

const digest = ref<Digest | null>(null);
const loading = ref(true);
const collapsed = ref(false);

const hasHighlights = computed(() =>
  (digest.value?.trends?.length ?? 0) > 0 || (digest.value?.anomalies?.length ?? 0) > 0
);

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
      <div
        class="w-1.5 h-1.5 rounded-full shrink-0"
        :class="hasHighlights ? 'bg-indigo-500 animate-pulse' : 'bg-indigo-500/60'"
      />
      <span class="text-xs text-gray-500 font-medium">{{ digest.date }} 回顾</span>
      <span
        v-if="hasHighlights"
        class="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-500/15 text-indigo-400 shrink-0"
      >有新发现</span>
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

      <!-- 趋势 -->
      <div v-if="digest.trends?.length" class="mt-2.5">
        <span class="text-[10px] text-gray-600 uppercase tracking-wide">趋势</span>
        <ul class="mt-1 space-y-0.5">
          <li
            v-for="(t, i) in digest.trends"
            :key="'t' + i"
            class="text-[11px] text-indigo-400 flex items-center gap-1"
          >
            <svg class="w-2.5 h-2.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
            {{ t }}
          </li>
        </ul>
      </div>

      <!-- 异常 -->
      <div v-if="digest.anomalies?.length" class="mt-2">
        <span class="text-[10px] text-gray-600 uppercase tracking-wide">注意</span>
        <ul class="mt-1 space-y-0.5">
          <li
            v-for="(a, i) in digest.anomalies"
            :key="'a' + i"
            class="text-[11px] text-amber-400 flex items-center gap-1"
          >
            <svg class="w-2.5 h-2.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {{ a }}
          </li>
        </ul>
      </div>

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
