<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, inject } from "vue";
import NoteCard from "../components/NoteCard.vue";

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
const filter = ref<"live" | "superseded" | "archived" | "all">("live");
const searchQuery = ref("");
const searchInputEl = ref<HTMLInputElement | null>(null);
const loading = ref(false);

// ── Toast ──
const toast = inject<(msg: string, type?: "info" | "success" | "error") => void>("toast", () => {});

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

// ── 分组 ──
const todayNotes = computed(() => {
  const today = new Date().toDateString();
  return notes.value.filter((n) => {
    try { return new Date(n.created_at).toDateString() === today; }
    catch { return false; }
  });
});

const activeNotes = computed(() => {
  return notes.value
    .filter((n) => n.status === "live" && !todayNotes.value.includes(n))
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
});

const supersededNotes = computed(() => {
  return notes.value.filter((n) => n.status === "superseded");
});

const archivedNotes = computed(() => {
  return notes.value.filter((n) => n.status === "archived");
});

// ── 过滤（用于搜索）──
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

// 是否处于搜索模式
const isSearching = computed(() => searchQuery.value.trim().length > 0);

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
        emit("note-selected", null as unknown as Note);
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

function formatRelative(s: string): string {
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  const now = Date.now();
  const diff = now - d.getTime();
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`;
  return formatDate(s);
}

function highlightMatches(text: string): string {
  if (!searchQuery.value.trim()) return text;
  const q = searchQuery.value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return text.replace(new RegExp(`(${q})`, "gi"), "<mark class='bg-indigo-500/30 text-indigo-200 rounded-sm px-0.5'>$1</mark>");
}

const SECTION_COLORS: Record<string, string> = {
  Today: "#7C9CFF",
  "Active Ideas": "#70E0A3",
  Evolving: "#FFB86B",
  Archived: "#9AA4B2",
};
</script>

<template>
  <div class="flex flex-col h-full min-h-0">
    <!-- 搜索 -->
    <div class="px-2 pt-2 pb-1">
      <div class="relative">
        <svg
          class="w-3 h-3 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
          style="color: #9AA4B2; opacity: 0.4"
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          ref="searchInputEl"
          v-model="searchQuery"
          type="text"
          placeholder="搜索笔记… (Ctrl+K)"
          class="w-full rounded-lg pl-8 pr-3 py-1.5 text-xs outline-none transition-colors border"
          style="background: rgba(255,255,255,0.03); border-color: rgba(255,255,255,0.06); color: #F4F6FA"
          @focus="(e) => (e.target as HTMLInputElement).style.borderColor = 'rgba(124,156,255,0.3)'"
          @blur="(e) => (e.target as HTMLInputElement).style.borderColor = 'rgba(255,255,255,0.06)'"
        />
        <button
          v-if="searchQuery"
          class="absolute right-2 top-1/2 -translate-y-1/2"
          style="color: #9AA4B2"
          @click="searchQuery = ''"
        >
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>

    <!-- 内容区 -->
    <div class="flex-1 overflow-y-auto px-1.5 pb-2">

      <!-- ──── 搜索模式：平铺列表 ──── -->
      <template v-if="isSearching">
        <ul class="space-y-0.5">
          <li
            v-for="note in filtered"
            :key="note.id"
            class="group px-2.5 py-2 rounded-lg cursor-pointer transition-colors border"
            :class="[
              selectedId === note.id
                ? 'border-indigo-500/20'
                : 'border-transparent hover:border-white/[0.04]',
              note.status === 'archived' ? 'opacity-50' : '',
            ]"
            :style="{ background: selectedId === note.id ? 'rgba(124,156,255,0.08)' : 'transparent' }"
            @click="selectNote(note)"
            @contextmenu="onContextMenu($event, note)"
          >
            <div class="flex items-start justify-between gap-1.5">
              <span
                class="text-xs leading-snug flex-1 line-clamp-2"
                style="color: #F4F6FA"
                v-html="searchQuery ? highlightMatches(note.title) : note.title"
              />
              <span class="text-[9px] shrink-0 mt-0.5" style="color: #9AA4B2">{{ formatDate(note.created_at) }}</span>
            </div>
            <p v-if="note.content" class="text-[10px] mt-1 line-clamp-1 leading-relaxed" style="color: #9AA4B2">
              {{ note.content.slice(0, 80) }}
            </p>
            <div v-if="note.tags?.length" class="flex gap-1 mt-1.5 flex-wrap">
              <span
                v-for="tag in note.tags"
                :key="tag"
                class="text-[9px] px-1.5 py-0.5 rounded-full border"
                style="background: rgba(255,255,255,0.03); color: #9AA4B2; border-color: rgba(255,255,255,0.04)"
              >{{ tag }}</span>
            </div>
          </li>
        </ul>
        <div v-if="!filtered.length" class="px-4 py-8 text-center">
          <p class="text-xs" style="color: #9AA4B2">没有匹配的笔记</p>
        </div>
      </template>

      <!-- ──── 正常模式：分组视图 ──── -->
      <template v-else>
        <!-- Today -->
        <section v-if="todayNotes.length" class="mb-3">
          <div class="flex items-center gap-2 px-2 pb-1.5">
            <span class="w-1.5 h-1.5 rounded-full" :style="{ background: SECTION_COLORS['Today'] }" />
            <span class="text-[10px] font-semibold uppercase tracking-wider" style="color: #9AA4B2">Today</span>
            <span class="text-[9px] ml-auto" style="color: #9AA4B2; opacity: 0.5">{{ todayNotes.length }}</span>
          </div>
          <NoteCard
            v-for="note in todayNotes"
            :key="note.id"
            :note="note"
            :selected="selectedId === note.id"
            @select="selectNote"
            @contextmenu="onContextMenu($event, note)"
          />
        </section>

        <!-- Active Ideas -->
        <section v-if="activeNotes.length" class="mb-3">
          <div class="flex items-center gap-2 px-2 pb-1.5">
            <span class="w-1.5 h-1.5 rounded-full" :style="{ background: SECTION_COLORS['Active Ideas'] }" />
            <span class="text-[10px] font-semibold uppercase tracking-wider" style="color: #9AA4B2">Active Ideas</span>
            <span class="text-[9px] ml-auto" style="color: #9AA4B2; opacity: 0.5">{{ activeNotes.length }}</span>
          </div>
          <NoteCard
            v-for="note in activeNotes"
            :key="note.id"
            :note="note"
            :selected="selectedId === note.id"
            @select="selectNote"
            @contextmenu="onContextMenu($event, note)"
          />
        </section>

        <!-- Evolving (superseded) -->
        <section v-if="supersededNotes.length" class="mb-3">
          <div class="flex items-center gap-2 px-2 pb-1.5">
            <span class="w-1.5 h-1.5 rounded-full" :style="{ background: SECTION_COLORS['Evolving'] }" />
            <span class="text-[10px] font-semibold uppercase tracking-wider" style="color: #9AA4B2">Evolving</span>
            <span class="text-[9px] ml-auto" style="color: #9AA4B2; opacity: 0.5">{{ supersededNotes.length }}</span>
          </div>
          <NoteCard
            v-for="note in supersededNotes"
            :key="note.id"
            :note="note"
            :selected="selectedId === note.id"
            @select="selectNote"
            @contextmenu="onContextMenu($event, note)"
          />
        </section>

        <!-- Archived -->
        <section v-if="archivedNotes.length">
          <details class="group/section" open>
            <summary class="flex items-center gap-2 px-2 pb-1.5 cursor-pointer select-none">
              <span class="w-1.5 h-1.5 rounded-full" :style="{ background: SECTION_COLORS['Archived'] }" />
              <span class="text-[10px] font-semibold uppercase tracking-wider" style="color: #9AA4B2">Archived</span>
              <span class="text-[9px]" style="color: #9AA4B2; opacity: 0.5">{{ archivedNotes.length }}</span>
              <svg class="w-2.5 h-2.5 ml-auto transition-transform group-open/section:rotate-180" style="color: #9AA4B2; opacity: 0.4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </summary>
            <NoteCard
              v-for="note in archivedNotes"
              :key="note.id"
              :note="note"
              :selected="selectedId === note.id"
              @select="selectNote"
              @contextmenu="onContextMenu($event, note)"
            />
          </details>
        </section>

        <!-- 空状态 -->
        <div v-if="!notes.length && !loading" class="px-4 py-12 text-center">
          <div class="w-10 h-10 rounded-2xl mx-auto mb-3 flex items-center justify-center" style="background: rgba(255,255,255,0.02)">
            <svg class="w-5 h-5" style="color: #9AA4B2; opacity: 0.3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <p class="text-xs" style="color: #9AA4B2">
            还没有笔记
          </p>
          <p class="text-[10px] mt-1" style="color: #9AA4B2; opacity: 0.5">
            发送第一条消息开始捕捉想法
          </p>
        </div>
      </template>

      <!-- 加载 -->
      <div v-if="loading" class="px-4 py-8 text-center">
        <span class="text-xs animate-pulse" style="color: #9AA4B2">加载中…</span>
      </div>
    </div>

    <!-- 右键菜单 -->
    <Teleport to="body">
      <div
        v-if="contextMenu"
        class="fixed z-50 min-w-[140px] py-1 rounded-xl shadow-2xl border"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px', background: '#20242D', borderColor: '#2C3240' }"
        @click.stop
      >
        <button
          class="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] transition-colors text-left hover:brightness-110"
          style="color: #9AA4B2"
          @click="copyContent(contextMenu.note)"
        >
          <svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          复制内容
        </button>
        <button
          class="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] transition-colors text-left hover:brightness-110"
          style="color: #9AA4B2"
          @click="archiveNote(contextMenu.note)"
        >
          <svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8l1 12a2 2 0 002 2h8a2 2 0 002-2L19 8" />
          </svg>
          {{ contextMenu.note.status === 'archived' ? '取消归档' : '归档' }}
        </button>
        <div class="h-px my-1" style="background: rgba(255,255,255,0.06)" />
        <button
          class="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] transition-colors text-left hover:brightness-110"
          style="color: #FF6B6B"
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

