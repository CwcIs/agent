<script setup lang="ts">
import { ref, provide, onMounted, onUnmounted } from "vue";
import ChatView from "./views/ChatView.vue";
import NoteListView from "./views/NoteListView.vue";
import NoteDetailPanel from "./views/NoteDetailPanel.vue";
import DailyDigestPanel from "./views/DailyDigestPanel.vue";
import ToastProvider from "./components/ToastProvider.vue";

interface Note {
  id: string;
  title: string;
  content: string;
  tags: string[];
  status: string;
  created_at: string;
}

const sidebarOpen = ref(true);
const selectedNote = ref<Note | null>(null);
const chatRef = ref<InstanceType<typeof ChatView> | null>(null);
const noteListRef = ref<InstanceType<typeof NoteListView> | null>(null);
const toastRef = ref<InstanceType<typeof ToastProvider> | null>(null);

function handleFollowUp(q: string) {
  chatRef.value?.sendWithText(q);
}

function handleNoteSelected(note: Note) {
  selectedNote.value = note;
}

function handleDetailClose() {
  selectedNote.value = null;
}

function handleNoteUpdated() {
  noteListRef.value?.refresh();
}

// ── 全局键盘快捷键 ──
function onKeydown(e: KeyboardEvent) {
  // Ctrl+/  — 聚焦聊天输入
  if (e.ctrlKey && e.key === "/") {
    e.preventDefault();
    (document.querySelector(".chat-input") as HTMLTextAreaElement)?.focus();
    return;
  }
  // Ctrl+K — 聚焦笔记搜索
  if (e.ctrlKey && e.key === "k") {
    e.preventDefault();
    noteListRef.value?.focusSearch();
    return;
  }
  // Escape — 关闭详情面板
  if (e.key === "Escape" && selectedNote.value) {
    selectedNote.value = null;
    return;
  }
}

onMounted(() => document.addEventListener("keydown", onKeydown));
onUnmounted(() => document.removeEventListener("keydown", onKeydown));

// Toast 能力注入给子组件
function toast(message: string, type: "info" | "success" | "error" = "info") {
  toastRef.value?.show(message, type);
}
provide("toast", toast);
</script>

<template>
  <div
    class="flex h-screen bg-[#0d0d0d] text-gray-100 overflow-hidden"
    style="font-family: -apple-system, 'SF Pro Text', system-ui, sans-serif;"
  >
    <!-- 左侧笔记栏 -->
    <transition name="sidebar">
      <aside
        v-show="sidebarOpen"
        class="flex flex-col w-56 shrink-0 border-r border-white/[0.06] bg-[#111111]"
      >
        <div class="flex items-center justify-between px-3 h-12 border-b border-white/[0.06] shrink-0">
          <span class="text-[11px] font-semibold text-gray-500 tracking-[0.12em] uppercase">笔记库</span>
          <button
            class="p-1 rounded hover:bg-white/5 text-gray-600 hover:text-gray-400 transition-colors"
            @click="sidebarOpen = false"
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 19l-7-7 7-7" />
            </svg>
          </button>
        </div>
        <NoteListView
          ref="noteListRef"
          :selected-id="selectedNote?.id ?? null"
          @note-selected="handleNoteSelected"
        />
      </aside>
    </transition>

    <!-- 主区域 -->
    <main class="flex-1 flex flex-col min-w-0">
      <!-- 顶栏 -->
      <header class="flex items-center gap-3 px-4 h-12 border-b border-white/[0.06] shrink-0">
        <button
          v-if="!sidebarOpen"
          class="p-1 rounded hover:bg-white/5 text-gray-600 hover:text-gray-400 transition-colors"
          @click="sidebarOpen = true"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <span class="text-sm font-medium text-gray-300">知识工作台</span>
        <span class="text-[10px] text-gray-600 font-mono bg-white/[0.03] px-1.5 py-0.5 rounded">Ctrl+/ 聚焦输入</span>
      </header>

      <!-- 每日回顾 -->
      <DailyDigestPanel @follow-up="handleFollowUp" />

      <!-- Chat -->
      <ChatView ref="chatRef" @note-saved="noteListRef?.refresh()" />
    </main>

    <!-- 右侧详情面板 -->
    <NoteDetailPanel
      :note="selectedNote"
      @close="handleDetailClose"
      @updated="handleNoteUpdated"
    />

    <!-- 全局 Toast -->
    <ToastProvider ref="toastRef" />
  </div>
</template>

<style>
* { box-sizing: border-box; }
body { margin: 0; background: #0d0d0d; }

.sidebar-enter-active,
.sidebar-leave-active {
  transition: width 0.2s ease, opacity 0.2s ease;
  overflow: hidden;
}
.sidebar-enter-from,
.sidebar-leave-to {
  width: 0;
  opacity: 0;
}
.sidebar-enter-to,
.sidebar-leave-from {
  width: 224px;
  opacity: 1;
}

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.18); }
</style>
