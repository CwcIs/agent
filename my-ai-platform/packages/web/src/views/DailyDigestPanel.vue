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
const expanded = ref(true);

const hasHighlights = computed(() =>
  (digest.value?.trends?.length ?? 0) > 0 || (digest.value?.anomalies?.length ?? 0) > 0
);

onMounted(async () => {
  try {
    const resp = await fetch("/digest");
    if (resp.ok) {
      const data = await resp.json();
      if (data.narrative || data.trends?.length || data.anomalies?.length) {
        digest.value = data;
      }
    }
  } catch {
    digest.value = null;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <!-- 加载中 -->
  <div
    v-if="loading"
    class="mx-4 mt-4 px-4 py-3 rounded-xl border flex items-center gap-2 shrink-0"
    style="background: rgba(255,255,255,0.02); border-color: var(--border-subtle)"
  >
    <div class="w-1.5 h-1.5 rounded-full animate-pulse-glow" style="background: var(--agent-knowledge)" />
    <span class="text-[11px]" style="color: var(--text-muted)">生成今日回顾…</span>
  </div>

  <!-- 有数据 -->
  <div
    v-else-if="digest"
    class="mx-4 mt-4 rounded-xl overflow-hidden shrink-0 transition-all border"
    :style="{
      background: hasHighlights ? 'rgba(124,156,255,0.03)' : 'rgba(255,255,255,0.02)',
      borderColor: hasHighlights ? 'rgba(124,156,255,0.1)' : 'var(--border-subtle)',
    }"
  >
    <!-- 头部 -->
    <button
      class="w-full flex items-center gap-2.5 px-4 py-2.5 hover:brightness-110 transition-all text-left"
      @click="expanded = !expanded"
    >
      <div
        class="w-1.5 h-1.5 rounded-full shrink-0"
        :class="hasHighlights ? 'animate-pulse-glow' : ''"
        :style="{ background: hasHighlights ? 'var(--agent-knowledge)' : 'var(--text-muted)' }"
      />
      <span class="text-xs font-medium" style="color: var(--text-muted)">{{ digest.date }} 回顾</span>
      <span v-if="hasHighlights" class="text-[10px] px-1.5 py-0.5 rounded-full shrink-0 border"
        style="background: rgba(124,156,255,0.1); color: var(--agent-knowledge); border-color: rgba(124,156,255,0.15)"
      >新发现</span>
      <span class="text-[10px]" style="color: var(--text-muted); opacity: 0.5">{{ digest.noteCount }} 条笔记</span>
      <svg
        class="w-3 h-3 ml-auto transition-transform"
        :class="expanded ? '' : '-rotate-90'"
        style="color: var(--text-muted); opacity: 0.4"
        fill="none" stroke="currentColor" viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
      </svg>
    </button>

    <!-- 展开内容 -->
    <div v-if="expanded" class="px-4 pb-3 space-y-2.5">
      <!-- 叙述 -->
      <p class="text-[11px] leading-relaxed" style="color: var(--text-muted)">{{ digest.narrative }}</p>

      <!-- 趋势 -->
      <div v-if="digest.trends?.length">
        <span class="text-[9px] uppercase tracking-wide font-medium" style="color: var(--text-muted)">趋势</span>
        <ul class="mt-1 space-y-0.5">
          <li
            v-for="(t, i) in digest.trends"
            :key="'t' + i"
            class="text-[11px] flex items-start gap-1.5"
            style="color: var(--agent-knowledge)"
          >
            <svg class="w-2.5 h-2.5 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
            {{ t }}
          </li>
        </ul>
      </div>

      <!-- 异常 -->
      <div v-if="digest.anomalies?.length">
        <span class="text-[9px] uppercase tracking-wide font-medium" style="color: var(--text-muted)">注意</span>
        <ul class="mt-1 space-y-0.5">
          <li
            v-for="(a, i) in digest.anomalies"
            :key="'a' + i"
            class="text-[11px] flex items-start gap-1.5"
            style="color: var(--color-warning)"
          >
            <svg class="w-2.5 h-2.5 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {{ a }}
          </li>
        </ul>
      </div>

      <!-- 引用笔记 -->
      <div v-if="digest.citedNotes?.length" class="flex flex-wrap gap-1.5 mt-1">
        <span
          v-for="n in digest.citedNotes"
          :key="n.noteId"
          class="text-[10px] px-2 py-0.5 rounded-full border"
          style="background: rgba(255,255,255,0.03); color: var(--text-muted); border-color: rgba(255,255,255,0.04)"
        >{{ n.title }}</span>
      </div>

      <!-- Follow-up 问题 -->
      <div v-if="digest.followUps?.length" class="flex flex-wrap gap-1.5 pt-1">
        <button
          v-for="(q, i) in digest.followUps"
          :key="i"
          class="text-[10px] px-2.5 py-1 rounded-full border transition-all hover:brightness-110 text-left"
          style="border-color: rgba(124,156,255,0.2); color: var(--agent-knowledge)"
          @click="emit('followUp', q)"
        >{{ q }}</button>
      </div>
    </div>
  </div>
</template>
