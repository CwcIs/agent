<script setup lang="ts">
import { ref, computed, onMounted } from "vue";

interface Note {
  id: string;
  title: string;
  tags: string[];
  status: string;
  createdAt: string;
}

const notes = ref<Note[]>([]);
const filter = ref<"live" | "superseded" | "archived" | "all">("live");

const filtered = computed(() =>
  filter.value === "all" ? notes.value : notes.value.filter((n) => n.status === filter.value)
);

const statusLabels: Record<string, string> = {
  live: "有效",
  superseded: "已覆盖",
  archived: "归档",
  all: "全部",
};

onMounted(async () => {
  try {
    const resp = await fetch("/notes");
    const data = await resp.json();
    notes.value = data.notes ?? [];
  } catch {
    notes.value = [];
  }
});

function formatDate(s: string) {
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : `${d.getMonth() + 1}/${d.getDate()}`;
}
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- 过滤标签 -->
    <div class="flex gap-1 px-3 pt-3 pb-2">
      <button
        v-for="s in (['live', 'all'] as const)"
        :key="s"
        :class="[
          'px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors',
          filter === s
            ? 'bg-white/10 text-gray-200'
            : 'text-gray-600 hover:text-gray-400'
        ]"
        @click="filter = s"
      >
        {{ statusLabels[s] }}
      </button>
    </div>

    <!-- 列表 -->
    <ul class="flex-1 overflow-y-auto px-2 pb-3 space-y-0.5">
      <li
        v-for="note in filtered"
        :key="note.id"
        class="group px-3 py-2.5 rounded-lg cursor-pointer hover:bg-white/[0.04] transition-colors"
        :class="{ 'opacity-40': note.status !== 'live' }"
      >
        <div class="flex items-start justify-between gap-2">
          <span class="text-sm text-gray-300 truncate leading-snug">{{ note.title }}</span>
          <span class="text-[10px] text-gray-700 shrink-0 mt-0.5">{{ formatDate(note.createdAt) }}</span>
        </div>
        <div v-if="note.tags?.length" class="flex gap-1 mt-1.5 flex-wrap">
          <span
            v-for="tag in note.tags"
            :key="tag"
            class="text-[10px] px-1.5 py-0.5 bg-white/[0.05] text-gray-500 rounded"
          >
            {{ tag }}
          </span>
        </div>
      </li>
    </ul>

    <div v-if="!filtered.length" class="px-4 py-6 text-center">
      <p class="text-xs text-gray-700">还没有笔记</p>
    </div>
  </div>
</template>
