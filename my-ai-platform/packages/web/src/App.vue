<script setup lang="ts">
import { computed, ref, provide, onMounted, onUnmounted } from "vue";
import AppShell from "./components/AppShell.vue";
import LeftRail from "./components/LeftRail.vue";
import InsightDrawer from "./components/InsightDrawer.vue";
import ChatView from "./views/ChatView.vue";
import NoteDetailPanel from "./views/NoteDetailPanel.vue";
import DailyDigestPanel from "./views/DailyDigestPanel.vue";
import CommercialPrototype from "./views/CommercialPrototype.vue";
import TraceConsole from "./views/TraceConsole.vue";
import GraphView from "./views/GraphView.vue";
import ProfileView from "./views/ProfileView.vue";
import AdminView from "./views/AdminView.vue";
import TopStatusBar from "./components/TopStatusBar.vue";
import ToastProvider from "./components/ToastProvider.vue";
import WorkbenchHub from "./components/WorkbenchHub.vue";
import { useChatThreads } from "./composables/useChatThreads";

interface Note {
  id: string;
  title: string;
  content: string;
  tags: string[];
  status: string;
  knowledge_status?: string;
  created_at: string;
}

const sidebarOpen = ref(true);
const drawerOpen = ref(false);
const selectedNote = ref<Note | null>(null);
const chatRef = ref<InstanceType<typeof ChatView> | null>(null);
const noteListRef = ref<InstanceType<typeof LeftRail> | null>(null);
const toastRef = ref<InstanceType<typeof ToastProvider> | null>(null);
const showCommercialPrototype = ref(false);
const showTraceConsole = ref(false);
const initialTraceId = ref<string | null>(null);
const showGraphView = ref(false);
const showProfileView = ref(false);
const showAdminView = ref(false);
const showWorkbenchHub = ref(false);
const chatStreaming = ref(false);
const runningAgents = ref<string[]>([]);
const {
  activeSessionId,
  threads,
  loadingThreads,
  refreshThreads,
  selectThread,
  createThread,
  updateThread,
} = useChatThreads();
const activeThread = computed(() =>
  threads.value.find(thread => thread.session_id === activeSessionId.value)
);
const activeThreadTitle = computed(() => activeThread.value?.title || "New thought");

// Daily digest state
const showDigest = ref(false);
const dailyNoteCount = ref(0);
const dailyTrendCount = ref(0);
const dailyAnomalyCount = ref(0);
const pendingReviewCount = ref(0);
const smartBadges = ref<Array<{ type: string; label: string; priority: string }>>([]);
const notificationsEnabled = ref(false);
let pollInterval: ReturnType<typeof setInterval> | null = null;
let lastDigestCheck = ""; // track when we last checked for digest

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

function handleGraphSelectNote(noteId: string) {
  // Close graph and open note in detail
  showGraphView.value = false;
  fetch(`/notes/${noteId}/relations`).catch(() => {});
  // Try to find title and show in detail
  fetch(`/notes`).then(r => r.json()).then(data => {
    const note = (data.notes || []).find((n: Note) => n.id === noteId);
    if (note) {
      selectedNote.value = note;
      drawerOpen.value = true;
    }
  }).catch(() => {});
}

function openTraceConsole(traceId?: string) {
  initialTraceId.value = traceId || null;
  showTraceConsole.value = true;
}

function handleNewThread() {
  createThread();
  selectedNote.value = null;
  drawerOpen.value = false;
}

function handleSelectThread(sessionId: string) {
  selectThread(sessionId);
  selectedNote.value = null;
  drawerOpen.value = false;
}

async function handleUpdateThread(
  sessionId: string,
  patch: { title?: string; pinned?: boolean; archived?: boolean },
) {
  try {
    await updateThread(sessionId, patch);
    toast(patch.archived ? "任务已归档" : "任务已更新", "success");
  } catch {
    toast("任务更新失败", "error");
  }
}

function handleHubNavigation(target: "trace" | "graph" | "profile" | "admin" | "digest") {
  showWorkbenchHub.value = false;
  if (target === "trace") showTraceConsole.value = true;
  if (target === "graph") showGraphView.value = true;
  if (target === "profile") showProfileView.value = true;
  if (target === "admin") showAdminView.value = true;
  if (target === "digest") showDigest.value = true;
}

function handleChatStatus(status: { streaming: boolean; runningAgents: string[] }) {
  chatStreaming.value = status.streaming;
  runningAgents.value = status.runningAgents;
}

function syncResponsiveLayout() {
  if (window.innerWidth < 760) sidebarOpen.value = false;
}

// 鈹€鈹€ Global Keyboard Shortcuts 鈹€鈹€
function onKeydown(e: KeyboardEvent) {
  // Ctrl+/ focus chat input
  if (e.ctrlKey && e.key === "/") {
    e.preventDefault();
    (document.querySelector(".chat-input") as HTMLTextAreaElement)?.focus();
    return;
  }
  // Ctrl+K focus note search
  if (e.ctrlKey && e.key === "k") {
    e.preventDefault();
    noteListRef.value?.focusSearch();
    return;
  }
  // Ctrl+Shift+T toggle Trace Console
  if (e.ctrlKey && e.shiftKey && e.key === "T") {
    e.preventDefault();
    showTraceConsole.value = !showTraceConsole.value;
    return;
  }
  // Ctrl+Shift+G toggle GraphView
  if (e.ctrlKey && e.shiftKey && e.key === "G") {
    e.preventDefault();
    showGraphView.value = !showGraphView.value;
    return;
  }
  // Ctrl+Shift+P toggle ProfileView
  if (e.ctrlKey && e.shiftKey && e.key === "P") {
    e.preventDefault();
    showProfileView.value = !showProfileView.value;
    return;
  }
  // Ctrl+Shift+A toggle AdminView
  if (e.ctrlKey && e.shiftKey && e.key === "A") {
    e.preventDefault();
    showAdminView.value = !showAdminView.value;
    return;
  }
  // Escape close drawer or overlays
  if (e.key === "Escape") {
    if (showTraceConsole.value) { showTraceConsole.value = false; return; }
    if (showGraphView.value) { showGraphView.value = false; return; }
    if (showAdminView.value) { showAdminView.value = false; return; }
    if (showProfileView.value) { showProfileView.value = false; return; }
    if (showWorkbenchHub.value) { showWorkbenchHub.value = false; return; }
    if (drawerOpen.value) { handleDetailClose(); return; }
    return;
  }
}

onMounted(() => {
  syncResponsiveLayout();
  const params = new URLSearchParams(window.location.search);
  showCommercialPrototype.value = params.get("prototype") === "1";
  showTraceConsole.value = params.get("trace") === "1";
  initialTraceId.value = params.get("traceId");
  showGraphView.value = params.get("graph") === "1";
  document.addEventListener("keydown", onKeydown);
  window.addEventListener("resize", syncResponsiveLayout);
  fetchDailyBadge();
  refreshThreads();

  // Request Web Notification permission
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission().then(perm => {
      notificationsEnabled.value = perm === "granted";
    });
  } else if ("Notification" in window && Notification.permission === "granted") {
    notificationsEnabled.value = true;
  }

  // Periodic polling for smart badges and new digest (every 5 minutes)
  pollInterval = setInterval(() => {
    fetchDailyBadge();
    checkNewDigest();
  }, 5 * 60 * 1000);

  // Check for new digest shortly after startup too
  setTimeout(() => checkNewDigest(), 30 * 1000);
});

onUnmounted(() => {
  document.removeEventListener("keydown", onKeydown);
  window.removeEventListener("resize", syncResponsiveLayout);
  if (pollInterval) clearInterval(pollInterval);
});

async function fetchDailyBadge() {
  try {
    const [digestResp, badgeResp, reviewResp] = await Promise.all([
      fetch("/digest"),
      fetch("/user/smart-badges"),
      fetch("/notes?knowledge_status=pending_review"),
    ]);
    if (digestResp.ok) {
      const data = await digestResp.json();
      dailyNoteCount.value = data.noteCount ?? 0;
      dailyTrendCount.value = data.trends?.length ?? 0;
      dailyAnomalyCount.value = data.anomalies?.length ?? 0;
    }
    if (badgeResp.ok) {
      const data = await badgeResp.json();
      smartBadges.value = data.badges || [];
    }
    if (reviewResp.ok) {
      const data = await reviewResp.json();
      pendingReviewCount.value = data.notes?.length ?? 0;
    }
  } catch { /* ignore */ }
}

async function checkNewDigest() {
  // Check if there's a new daily digest we should notify about
  try {
    const resp = await fetch("/digest");
    if (!resp.ok) return;
    const data = await resp.json();
    const dateKey = data.date || "";
    if (dateKey && dateKey !== lastDigestCheck && data.noteCount > 0) {
      lastDigestCheck = dateKey;
      if (notificationsEnabled.value && data.trends?.length) {
        try {
          new Notification("Daily Digest Ready", {
            body: `${data.noteCount} notes · ${data.trends.length} trends · ${data.collisions?.length || 0} collisions`,
            icon: "/favicon.ico",
          });
        } catch { /* notification failed */ }
      }
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
  <CommercialPrototype v-if="showCommercialPrototype" />

  <!-- Trace Console (full-screen overlay, toggled via Ctrl+Shift+T or ?trace=1) -->
  <div v-else-if="showTraceConsole" class="absolute inset-0 z-50 flex flex-col" style="background: var(--bg-app)">
    <TraceConsole :initial-trace-id="initialTraceId" @close="showTraceConsole = false" />
  </div>

  <!-- GraphView (full-screen overlay, toggled via Ctrl+Shift+G or ?graph=1) -->
  <div v-else-if="showGraphView" class="absolute inset-0 z-50 flex flex-col" style="background: var(--bg-app)">
    <GraphView @select-note="handleGraphSelectNote" />
  </div>

  <!-- ProfileView (full-screen overlay, toggled via Ctrl+Shift+P) -->
  <div v-else-if="showProfileView" class="absolute inset-0 z-50 flex flex-col" style="background: var(--bg-app)">
    <div class="flex items-center justify-between px-4 py-2 border-b shrink-0" style="border-color: var(--border-subtle)">
      <span class="text-xs" style="color: var(--text-muted)">Knowledge Profile</span>
      <button class="text-xs px-2 py-1 rounded hover:brightness-110" style="color: var(--text-tertiary)" @click="showProfileView = false">Close</button>
    </div>
    <ProfileView />
  </div>

  <!-- AdminView (full-screen overlay, toggled via Ctrl+Shift+A) -->
  <div v-else-if="showAdminView" class="absolute inset-0 z-50 flex flex-col" style="background: var(--bg-app)">
    <div class="flex items-center justify-between px-4 py-2 border-b shrink-0" style="border-color: var(--border-subtle)">
      <span class="text-xs" style="color: var(--text-muted)">Admin Panel</span>
      <button class="text-xs px-2 py-1 rounded hover:brightness-110" style="color: var(--text-tertiary)" @click="showAdminView = false">Close</button>
    </div>
    <AdminView />
  </div>

  <AppShell v-else :sidebar-open="sidebarOpen" :drawer-open="drawerOpen">
    <!-- Left Rail -->
    <template #left-rail>
      <LeftRail
        ref="noteListRef"
        :open="sidebarOpen"
        :selected-note-id="selectedNote?.id ?? null"
        :daily-note-count="dailyNoteCount"
        :daily-trend-count="dailyTrendCount"
        :threads="threads"
        :active-session-id="activeSessionId"
        :loading-threads="loadingThreads"
        @toggle="sidebarOpen = !sidebarOpen"
        @note-selected="handleNoteSelected"
        @toggle-digest="showDigest = !showDigest"
        @new-thread="handleNewThread"
        @select-thread="handleSelectThread"
        @update-thread="handleUpdateThread"
        @open-hub="showWorkbenchHub = true"
      />
    </template>

    <!-- Main Studio -->
    <template #studio>
      <main class="flex-1 flex flex-col min-w-0 min-h-0">
        <!-- Top Status Bar -->
        <TopStatusBar
          :streaming="chatStreaming"
          :running-agents="runningAgents"
          :session-id="'connected'"
          :daily-note-count="dailyNoteCount"
          :daily-trend-count="dailyTrendCount"
          :daily-anomaly-count="dailyAnomalyCount"
          :smart-badges="smartBadges"
          :thread-title="activeThreadTitle"
          :message-count="activeThread?.message_count ?? 0"
          :pending-review-count="pendingReviewCount"
          @toggle-digest="showDigest = !showDigest"
          @open-hub="showWorkbenchHub = true"
        >
          <template #toggle>
            <button
              v-if="!sidebarOpen"
              class="sidebar-toggle"
              :style="{ color: 'var(--text-secondary)' }"
              title="打开侧边栏"
              aria-label="打开侧边栏"
              @click="sidebarOpen = true"
            >
              ☰
            </button>
          </template>
        </TopStatusBar>

        <!-- Daily Digest (collapsible) -->
        <DailyDigestPanel
          v-if="showDigest"
          @follow-up="handleFollowUp"
        />

        <!-- Chat View -->
        <ChatView
          ref="chatRef"
          :session-id="activeSessionId"
          @note-saved="noteListRef?.refresh()"
          @conversation-updated="refreshThreads"
          @status-change="handleChatStatus"
          @trace-inspect="openTraceConsole"
        />
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

  <WorkbenchHub
    :open="showWorkbenchHub"
    :note-count="dailyNoteCount"
    :trend-count="dailyTrendCount"
    :anomaly-count="dailyAnomalyCount"
    :pending-review-count="pendingReviewCount"
    @close="showWorkbenchHub = false"
    @navigate="handleHubNavigation"
    @review-updated="fetchDailyBadge(); noteListRef?.refresh()"
  />

  <!-- Global Toast -->
  <ToastProvider ref="toastRef" />
</template>

<style scoped>
.sidebar-toggle {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 13px;
}
.sidebar-toggle:hover { background: var(--surface-hover); color: var(--text-primary); }
</style>

