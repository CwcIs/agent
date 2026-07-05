<script setup lang="ts">
import { ref, provide, onMounted, onUnmounted } from "vue";
import ChatView from "./views/ChatView.vue";
import NoteListView from "./views/NoteListView.vue";
import NoteDetailPanel from "./views/NoteDetailPanel.vue";
import DailyDigestPanel from "./views/DailyDigestPanel.vue";
import TopStatusBar from "./components/TopStatusBar.vue";
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

// Daily digest 状态
const showDigest = ref(false);
const dailyNoteCount = ref(0);
const dailyTrendCount = ref(0);
const dailyAnomalyCount = ref(0);

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

onMounted(() => {
  document.addEventListener("keydown", onKeydown);
  // 加载 daily digest 数据用于 badge
  fetchDailyBadge();
});

onUnmounted(() => document.removeEventListener("keydown", onKeydown));

async function fetchDailyBadge() {
  try {
    const resp = await fetch("/digest");
    if (resp.ok) {
      const data = await resp.json();
      dailyNoteCount.value = data.noteCount ?? 0;
      dailyTrendCount.value = data.trends?.length ?? 0;
      dailyAnomalyCount.value = data.anomalies?.length ?? 0;
    }
  } catch { /* ignore */ }
}

// Toast 能力注入给子组件
function toast(message: string, type: "info" | "success" | "error" = "info") {
  toastRef.value?.show(message, type);
}
provide("toast", toast);
</script>

<template>
  <div
    class="flex h-screen overflow-hidden"
    style="font-family: -apple-system, 'SF Pro Text', system-ui, sans-serif; background: var(--bg-root); color: var(--text-main)"
  >
    <!-- ── 左侧 Memory Stream ── -->
    <transition name="sidebar">
      <aside
        v-show="sidebarOpen"
        class="flex flex-col w-60 shrink-0 border-r"
        style="background: var(--bg-panel); border-color: var(--border-subtle)"
      >
        <div class="flex items-center justify-between px-3 h-11 border-b shrink-0" style="border-color: var(--border-subtle)">
          <span class="text-[10px] font-semibold uppercase tracking-[0.12em]" style="color: var(--text-muted)">
            Memory Stream
          </span>
          <button
            class="p-1 rounded hover:brightness-110 transition-all"
            style="color: var(--text-muted); opacity: 0.5"
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

    <!-- ── 主区域 ── -->
    <main class="flex-1 flex flex-col min-w-0">
      <!-- Top Status Bar -->
      <TopStatusBar
        :streaming="false"
        :running-agents="[]"
        :session-id="'connected'"
        :daily-note-count="dailyNoteCount"
        :daily-trend-count="dailyTrendCount"
        :daily-anomaly-count="dailyAnomalyCount"
        @toggle-digest="showDigest = !showDigest"
      >
        <template #toggle>
          <button
            v-if="!sidebarOpen"
            class="p-1 rounded hover:brightness-110 transition-all"
            style="color: var(--text-muted); opacity: 0.5"
            @click="sidebarOpen = true"
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </template>
      </TopStatusBar>

      <!-- 每日回顾（可折叠） -->
      <DailyDigestPanel
        v-if="showDigest"
        @follow-up="handleFollowUp"
      />

      <!-- Thinking Canvas -->
      <ChatView ref="chatRef" @note-saved="noteListRef?.refresh()" />
    </main>

    <!-- ── 右侧 Context Radar ── -->
    <NoteDetailPanel
      :note="selectedNote"
      @close="handleDetailClose"
      @updated="handleNoteUpdated"
    />

    <!-- 全局 Toast -->
    <ToastProvider ref="toastRef" />
  </div>
</template>
