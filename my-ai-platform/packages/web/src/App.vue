<script setup lang="ts">
import { ref, provide, onMounted, onUnmounted } from "vue";
import AppShell from "./components/AppShell.vue";
import LeftRail from "./components/LeftRail.vue";
import InsightDrawer from "./components/InsightDrawer.vue";
import ChatView from "./views/ChatView.vue";
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
const drawerOpen = ref(false);
const selectedNote = ref<Note | null>(null);
const chatRef = ref<InstanceType<typeof ChatView> | null>(null);
const noteListRef = ref<InstanceType<typeof LeftRail> | null>(null);
const toastRef = ref<InstanceType<typeof ToastProvider> | null>(null);

// Daily digest state
const showDigest = ref(false);
const dailyNoteCount = ref(0);
const dailyTrendCount = ref(0);
const dailyAnomalyCount = ref(0);

function handleFollowUp(q: string) {
  chatRef.value?.sendWithText(q);
}

function handleNoteSelected(note: Note) {
  selectedNote.value = note;
  drawerOpen.value = true;
}

function handleDetailClose() {
  selectedNote.value = null;
  drawerOpen.value = false;
}

function handleNoteUpdated() {
  noteListRef.value?.refresh();
}

// ── Global Keyboard Shortcuts ──
function onKeydown(e: KeyboardEvent) {
  // Ctrl+/ — focus chat input
  if (e.ctrlKey && e.key === "/") {
    e.preventDefault();
    (document.querySelector(".chat-input") as HTMLTextAreaElement)?.focus();
    return;
  }
  // Ctrl+K — focus note search
  if (e.ctrlKey && e.key === "k") {
    e.preventDefault();
    noteListRef.value?.focusSearch();
    return;
  }
  // Escape — close drawer
  if (e.key === "Escape" && drawerOpen.value) {
    handleDetailClose();
    return;
  }
}

onMounted(() => {
  document.addEventListener("keydown", onKeydown);
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

// Toast capability injected to children
function toast(message: string, type: "info" | "success" | "error" = "info") {
  toastRef.value?.show(message, type);
}
provide("toast", toast);
</script>

<template>
  <AppShell :sidebar-open="sidebarOpen" :drawer-open="drawerOpen">
    <!-- Left Rail -->
    <template #left-rail>
      <LeftRail
        ref="noteListRef"
        :open="sidebarOpen"
        :selected-note-id="selectedNote?.id ?? null"
        :daily-note-count="dailyNoteCount"
        :daily-trend-count="dailyTrendCount"
        @toggle="sidebarOpen = !sidebarOpen"
        @note-selected="handleNoteSelected"
        @toggle-digest="showDigest = !showDigest"
      />
    </template>

    <!-- Main Studio -->
    <template #studio>
      <main class="flex-1 flex flex-col min-w-0 min-h-0">
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
              class="p-1 rounded hover:brightness-110 transition-all opacity-40 hover:opacity-70"
              :style="{ color: 'var(--text-secondary)' }"
              @click="sidebarOpen = true"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          </template>
        </TopStatusBar>

        <!-- Daily Digest (collapsible) -->
        <DailyDigestPanel
          v-if="showDigest"
          @follow-up="handleFollowUp"
        />

        <!-- Chat View -->
        <ChatView ref="chatRef" @note-saved="noteListRef?.refresh()" />
      </main>
    </template>

    <!-- Right Insight Drawer -->
    <template #drawer>
      <InsightDrawer :open="drawerOpen" @close="handleDetailClose">
        <template #title>
          {{ selectedNote ? 'Note Detail' : 'Insight' }}
        </template>
        <NoteDetailPanel
          v-if="selectedNote"
          :note="selectedNote"
          @close="handleDetailClose"
          @updated="handleNoteUpdated"
        />
        <div
          v-else
          class="text-sm text-center py-12"
          :style="{ color: 'var(--text-tertiary)' }"
        >
          Select a note or chip to view details
        </div>
      </InsightDrawer>
    </template>
  </AppShell>

  <!-- Global Toast -->
  <ToastProvider ref="toastRef" />
</template>
