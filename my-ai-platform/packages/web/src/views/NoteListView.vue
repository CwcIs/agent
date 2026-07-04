<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, inject } from "vue";

interface Note {
  id: string;
  title: string;
  content: string;
  tags: string[];
  status: string;
  created_at: string;
}

const props = defineProps<{
  selectedId: string | null;
}>();

const emit = defineEmits<{
  "note-selected": [note: Note];
}>();

const notes = ref<Note[]>([]);
const filter = ref<"live" | "archived" | "all">("live");
const searchQuery = ref("");
const searchInputEl = ref<HTMLInputElement | null>(null);
const loading = ref(false);

// ── Toast (injected from App) ──
const toast = inject<(msg: string, type?: "info" | "success" | "error") => void>("toast", () => {});

// ── 暴露 focusSearch 供快捷键调用 ──
function focusSearch() {
  searchInputEl.value?.focus();
}
defineExpose({ refresh: fetchNotes, focusSearch });

// ── 右键菜单 ──
const contextMenu = ref<{ x: number; y: number; note: Note } | null>(null);

function onContextMenu(e: MouseEvent, note: Note) {
  e.preventDefault();
  e.stopPropagation();
  contextMenu.value = { x: e.clientX, y: e.clientY, note };
}

function closeContextMenu() {
  contextMenu.value = null;
}

onMounted(() => {
  document.addEventListener("click", closeContextMenu);
  document.addEventListener("scroll", closeContextMenu, true);
});

onUnmounted(() => {
  document.removeEventListener("click", closeContextMenu);
  document.removeEventListener("scroll", closeContextMenu, true);
});

// ── 数据 ──
async function fetchNotes() {
  loading.value = true;
  try {
    const resp = await fetch("/notes");
    const data = await resp.json();
    notes.value = data.notes ?? [];
  } catch {
    notes.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(fetchNotes);

// ── 过滤 ──
const filtered = computed(() => {
  let list = notes.value;
  if (filter.value !== "all") {
    list = list.filter((n) => n.status === filter.value);
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase();
    list = list.filter(
      (n) =>
        n.title.toLowerCase().includes(q) ||
        n.content.toLowerCase().includes(q) ||
        (n.tags || []).some((t) => t.toLowerCase().includes(q)),
    );
  }
  return list;
});

// ── 操作 ──
function selectNote(note: Note) {
  emit("note-selected", note);
}

async function archiveNote(note: Note) {
  const newStatus = note.status === "archived" ? "live" : "archived";
  const label = newStatus === "archived" ? "已归档" : "已恢复";
  try {
    const resp = await fetch(`/notes/${note.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    if (resp.ok) {
      note.status = newStatus;
      toast(`「${note.title}」${label}`, "success");
    }
  } catch { toast("操作失败", "error"); }
  closeContextMenu();
}

async function deleteNote(note: Note) {
  closeContextMenu();
  if (!confirm(`删除「${note.title}」？`)) return;
  try {
    const resp = await fetch(`/notes/${note.id}`, { method: "DELETE" });
    if (resp.ok) {
      notes.value = notes.value.filter((n) => n.id !== note.id);
      if (props.selectedId === note.id) {
        emit("note-selected", null as unknown as Note); // 触发取消选中
      }
      toast(`「${note.title}」已删除`, "success");
    }
  } catch { toast("删除失败", "error"); }
}

function copyContent(note: Note) {
  navigator.clipboard.writeText(note.content);
  closeContextMenu();
}

// ── 格式化 ──
function formatDate(s: string) {
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : `${d.getMonth() + 1}/${d.getDate()}`;
}

function highlightMatches(text: string): string {
  if (!searchQuery.value.trim()) return text;
  const q = searchQuery.value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return text.replace(new RegExp(`(${q})`, "gi"), "<mark class='bg-indigo-500/30 text-indigo-200 rounded-sm px-0.5'>$1</mark>");
}
</script>

<template>
  <div class="flex flex-col h-full min-h-0">
    <!-- 搜索 -->
    <div class="px-2 pt-2 pb-1">
      <div class="relative">
        <svg
          class="w-3 h-3 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-600 pointer-events-none"
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          ref="searchInputEl"
          v-model="searchQuery"
          type="text"
          placeholder="搜索笔记… (Ctrl+K)"
          class="w-full bg-white/[0.03] border border-white/[0.06] rounded-lg pl-8 pr-3 py-1.5 text-xs text-gray-300 placeholder-gray-600 outline-none focus:border-indigo-500/30 focus:bg-white/[0.04] transition-colors"
        />
        <button
          v-if="searchQuery"
          class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400"
          @click="searchQuery = ''"
        >
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>

    <!-- 过滤标签 -->
    <div class="flex gap-1 px-2 pb-2">
      <button
        v-for="s in (['live', 'archived', 'all'] as const)"
        :key="s"
        :class="[
          'px-2 py-0.5 rounded-full text-[10px] font-medium transition-colors',
          filter === s ? 'bg-white/10 text-gray-200' : 'text-gray-600 hover:text-gray-400',
        ]"
        @click="filter = s"
      >{{ s === 'live' ? '有效' : s === 'archived' ? '归档' : '全部' }}</button>
      <span class="ml-auto text-[10px] text-gray-700 self-center">{{ filtered.length }}</span>
    </div>

    <!-- 列表 -->
    <ul class="flex-1 overflow-y-auto px-1.5 pb-2 space-y-0.5">
      <li
        v-for="note in filtered"
        :key="note.id"
        class="group px-2.5 py-2 rounded-lg cursor-pointer transition-colors"
        :class="[
          selectedId === note.id
            ? 'bg-indigo-500/10 border border-indigo-500/20'
            : 'border border-transparent hover:bg-white/[0.03] hover:border-white/[0.04]',
          note.status === 'archived' ? 'opacity-50' : '',
        ]"
        @click="selectNote(note)"
        @contextmenu="onContextMenu($event, note)"
      >
        <div class="flex items-start justify-between gap-1.5">
          <span
            class="text-xs text-gray-300 leading-snug flex-1 line-clamp-2"
            v-html="searchQuery ? highlightMatches(note.title) : note.title"
          />
          <span class="text-[9px] text-gray-700 shrink-0 mt-0.5">{{ formatDate(note.created_at) }}</span>
        </div>
        <!-- 内容预览 -->
        <p
          v-if="note.content"
          class="text-[10px] text-gray-600 mt-1 line-clamp-1 leading-relaxed"
        >{{ note.content.slice(0, 80) }}</p>
        <!-- 标签 -->
        <div v-if="note.tags?.length" class="flex gap-1 mt-1.5 flex-wrap">
          <span
            v-for="tag in note.tags"
            :key="tag"
            class="text-[9px] px-1.5 py-0.5 rounded-full bg-white/[0.04] text-gray-500"
          >{{ tag }}</span>
        </div>
      </li>
    </ul>

    <!-- 空状态 -->
    <div v-if="!loading && !filtered.length" class="px-4 py-8 text-center">
      <p class="text-xs text-gray-700">
        {{ searchQuery ? '没有匹配的笔记' : filter === 'live' ? '还没有笔记，发送第一条消息开始' : '暂无笔记' }}
      </p>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="px-4 py-8 text-center">
      <span class="text-xs text-gray-700 animate-pulse">加载中…</span>
    </div>

    <!-- 右键菜单 -->
    <Teleport to="body">
      <div
        v-if="contextMenu"
        class="fixed z-50 min-w-[140px] py-1 bg-[#1a1a1a] border border-white/[0.08] rounded-xl shadow-2xl backdrop-blur-sm"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop
      >
        <button
          class="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] text-gray-400 hover:text-gray-200 hover:bg-white/[0.04] transition-colors text-left"
          @click="copyContent(contextMenu.note)"
        >
          <svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          复制内容
        </button>
        <button
          class="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] text-gray-400 hover:text-gray-200 hover:bg-white/[0.04] transition-colors text-left"
          @click="archiveNote(contextMenu.note)"
        >
          <svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8l1 12a2 2 0 002 2h8a2 2 0 002-2L19 8" />
          </svg>
          {{ contextMenu.note.status === 'archived' ? '取消归档' : '归档' }}
        </button>
        <div class="h-px bg-white/[0.06] my-1" />
        <button
          class="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors text-left"
          @click="deleteNote(contextMenu.note)"
        >
          <svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
          删除
        </button>
      </div>
    </Teleport>
  </div>
</template>
