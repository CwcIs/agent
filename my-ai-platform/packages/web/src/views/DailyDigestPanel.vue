<script setup lang="ts">
import { ref, computed, onMounted } from "vue";

const emit = defineEmits<{ followUp: [q: string] }>();

interface Digest {
  label: string;
  date?: string;
  noteCount: number;
  narrative: string;
  followUps: string[];
  citedNotes: Array<{ noteId: string; title: string }>;
  trends: string[];
  anomalies: string[];
  collisions: Array<{
    id: string;
    note_a_id: string;
    note_b_id: string;
    score: number;
    connection: string;
    angle: string;
  }>;
  dueReviews?: Array<{ id: string; title: string; review_count: number; interval_days: number }>;
  writingSuggestions?: Array<{ topic: string; note_count: number }>;
}

const digest = ref<Digest | null>(null);
const loading = ref(true);
const expanded = ref(true);
const activeTab = ref<"daily" | "weekly" | "monthly">("daily");

const hasHighlights = computed(() =>
  (digest.value?.trends?.length ?? 0) > 0 ||
  (digest.value?.anomalies?.length ?? 0) > 0 ||
  (digest.value?.collisions?.length ?? 0) > 0
);

const collisionCount = computed(() => digest.value?.collisions?.length ?? 0);

const apiMap: Record<string, string> = {
  daily: "/digest",
  weekly: "/digest/weekly",
  monthly: "/digest/monthly",
};

const tabLabels: Record<string, string> = {
  daily: "日",
  weekly: "周",
  monthly: "月",
};

const angleLabels: Record<string, string> = {
  pattern: "模式",
  contradiction: "矛盾",
  synthesis: "合成",
  bridge: "桥接",
};

const angleColors: Record<string, string> = {
  pattern: "var(--agent-knowledge)",
  contradiction: "var(--agent-review)",
  synthesis: "#70E0A3",
  bridge: "#FFB86B",
};

async function loadDigest(tab: "daily" | "weekly" | "monthly") {
  loading.value = true;
  activeTab.value = tab;
  try {
    const resp = await fetch(apiMap[tab]);
    if (resp.ok) {
      const data = await resp.json();
      if (data.narrative || data.trends?.length || data.anomalies?.length || data.collisions?.length) {
        digest.value = data;
      }
    }
  } catch {
    digest.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(() => loadDigest("daily"));
</script>

<template>
  <!-- 加载中 -->
  <div
    v-if="loading"
    class="mx-4 mt-4 px-4 py-3 rounded-xl border flex items-center gap-2 shrink-0"
    style="background: rgba(255,255,255,0.02); border-color: var(--border-subtle)"
  >
    <div class="w-1.5 h-1.5 rounded-full animate-pulse-glow" style="background: var(--agent-knowledge)" />
    <span class="text-[11px]" style="color: var(--text-muted)">生成回顾…</span>
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
    <!-- 头部 + Tab 切换 -->
    <div class="flex items-center border-b" style="border-color: var(--border-subtle)">
      <button
        class="flex items-center gap-2.5 px-4 py-2.5 hover:brightness-110 transition-all text-left flex-1"
        @click="expanded = !expanded"
      >
        <div
          class="w-1.5 h-1.5 rounded-full shrink-0"
          :class="hasHighlights ? 'animate-pulse-glow' : ''"
          :style="{ background: hasHighlights ? 'var(--agent-knowledge)' : 'var(--text-muted)' }"
        />
        <span class="text-xs font-medium" style="color: var(--text-muted)">
          {{ digest.label === 'daily' ? (digest.date ?? '今日') + ' 回顾' : digest.label === 'weekly' ? '周回顾' : '月回顾' }}
        </span>
        <!-- Badges -->
        <span v-if="digest.trends?.length" class="text-[10px] px-1.5 py-0.5 rounded-full shrink-0 border"
          style="background: rgba(124,156,255,0.1); color: var(--agent-knowledge); border-color: rgba(124,156,255,0.15)"
        >{{ digest.trends.length }} 趋势</span>
        <span v-if="collisionCount" class="text-[10px] px-1.5 py-0.5 rounded-full shrink-0 border"
          style="background: rgba(112,224,163,0.1); color: #70E0A3; border-color: rgba(112,224,163,0.15)"
        >{{ collisionCount }} 碰撞</span>
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

      <!-- Tab pills -->
      <div class="flex gap-0.5 pr-2">
        <button
          v-for="tab in (['daily','weekly','monthly'] as const)"
          :key="tab"
          class="text-[10px] px-2 py-0.5 rounded-full transition-all border"
          :style="{
            background: activeTab === tab ? 'rgba(255,255,255,0.06)' : 'transparent',
            color: activeTab === tab ? 'var(--text-main)' : 'var(--text-tertiary)',
            borderColor: activeTab === tab ? 'rgba(255,255,255,0.1)' : 'transparent',
          }"
          @click="loadDigest(tab)"
        >{{ tabLabels[tab] }}</button>
      </div>
    </div>

    <!-- 展开内容 -->
    <div v-if="expanded" class="px-4 pb-3 space-y-2.5">
      <!-- 叙述 -->
      <p class="text-[11px] leading-relaxed" style="color: var(--text-muted)">{{ digest.narrative }}</p>

      <!-- Idea Collisions -->
      <div v-if="digest.collisions?.length">
        <span class="text-[9px] uppercase tracking-wide font-medium" style="color: #70E0A3">意外碰撞</span>
        <div class="mt-1 space-y-1">
          <div
            v-for="c in digest.collisions"
            :key="c.id"
            class="text-[10px] px-2 py-1 rounded-lg flex items-start gap-1.5"
            style="background: rgba(112,224,163,0.04); border: 1px solid rgba(112,224,163,0.08)"
          >
            <span class="text-[10px] px-1 rounded shrink-0 font-medium" :style="{ background: 'rgba(255,255,255,0.04)', color: angleColors[c.angle] || 'var(--text-muted)' }">
              {{ angleLabels[c.angle] || c.angle }}
            </span>
            <span style="color: var(--text-muted)">{{ c.connection }}</span>
            <span class="text-[9px] ml-auto shrink-0" style="color: var(--text-tertiary)">{{ c.score }}/10</span>
          </div>
        </div>
      </div>

      <!-- 趋势 -->
      <div v-if="digest.trends?.length">
        <span class="text-[9px] uppercase tracking-wide font-medium" style="color: var(--text-muted)">趋势 & 探索</span>
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

      <!-- 待复习 -->
      <div v-if="digest.dueReviews?.length">
        <span class="text-[9px] uppercase tracking-wide font-medium" style="color: var(--color-warning)">待复习</span>
        <div class="mt-1 space-y-0.5">
          <div
            v-for="r in digest.dueReviews"
            :key="r.id"
            class="text-[10px] px-2 py-1 rounded-lg flex items-center gap-1.5"
            style="background: rgba(255,184,107,0.04); border: 1px solid rgba(255,184,107,0.08)"
          >
            <span style="color: var(--text-muted)">{{ r.title }}</span>
            <span class="text-[9px] ml-auto shrink-0" style="color: var(--text-tertiary)">
              间隔 {{ r.interval_days }}d · 已复习 {{ r.review_count }} 次
            </span>
          </div>
        </div>
      </div>

      <!-- 写作灵感 -->
      <div v-if="digest.writingSuggestions?.length">
        <span class="text-[9px] uppercase tracking-wide font-medium" style="color: var(--agent-brain)">写作灵感</span>
        <div class="mt-1 space-y-0.5">
          <button
            v-for="ws in digest.writingSuggestions"
            :key="ws.topic"
            class="text-[10px] px-2 py-1 rounded-lg flex items-center gap-1.5 w-full text-left transition-all hover:brightness-110"
            style="background: rgba(171,137,245,0.04); border: 1px solid rgba(171,137,245,0.08); color: var(--agent-brain)"
            @click="emit('followUp', `帮我把「${ws.topic}」的 ${ws.note_count} 条笔记写成一篇综述`)"
          >
            <svg class="w-2.5 h-2.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
            </svg>
            <span>「{{ ws.topic }}」已有 {{ ws.note_count }} 条笔记，可以写综述了</span>
          </button>
        </div>
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
