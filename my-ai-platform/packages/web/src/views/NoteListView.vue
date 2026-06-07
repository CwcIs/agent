<script setup lang="ts">
/**
 * 笔记列表 — 左侧面板
 * 显示 status=live 的笔记，支持过滤 superseded/archived
 */
import { ref, onMounted } from "vue";

interface Note {
  id: string;
  title: string;
  tags: string[];
  status: string;
  createdAt: string;
}

const notes = ref<Note[]>([]);
const filter = ref<"live" | "superseded" | "archived" | "all">("live");

onMounted(async () => {
  const resp = await fetch("/notes");
  const data = await resp.json();
  notes.value = data.notes;
});
</script>

<template>
  <div>
    <h2 class="text-lg font-semibold mb-3">📒 笔记</h2>

    <!-- 状态过滤 -->
    <div class="flex gap-1 mb-3 text-xs">
      <button
        v-for="s in (['live', 'superseded', 'archived', 'all'] as const)"
        :key="s"
        :class="['px-2 py-1 rounded', filter === s ? 'bg-blue-100 text-blue-700' : 'text-gray-500']"
        @click="filter = s"
      >
        {{ s === 'all' ? '全部' : s }}
      </button>
    </div>

    <!-- 笔记列表 -->
    <ul class="space-y-2">
      <li
        v-for="note in notes"
        :key="note.id"
        class="p-2 rounded border hover:border-blue-300 cursor-pointer"
        :class="{ 'opacity-50': note.status !== 'live' }"
      >
        <div class="text-sm font-medium truncate">{{ note.title }}</div>
        <div class="flex gap-1 mt-1">
          <span
            v-for="tag in note.tags"
            :key="tag"
            class="text-xs px-1.5 py-0.5 bg-gray-100 rounded"
          >
            {{ tag }}
          </span>
        </div>
        <div class="text-xs text-gray-400 mt-1">{{ note.createdAt }}</div>
      </li>
    </ul>

    <p v-if="!notes.length" class="text-sm text-gray-400 mt-4">
      还没有笔记，去 Chat 里写第一条吧
    </p>
  </div>
</template>
