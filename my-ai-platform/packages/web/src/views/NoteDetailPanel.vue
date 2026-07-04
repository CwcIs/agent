<script setup lang="ts">
import { ref, watch, nextTick } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";

interface Note {
  id: string;
  title: string;
  content: string;
  tags: string[];
  status: string;
  created_at: string;
}

interface Relation {
  id: string;
  to_id?: string;
  to_title?: string;
  from_id?: string;
  from_title?: string;
  relation: string;
  created_at: string;
}

interface RelationsData {
  outgoing: Relation[];
  incoming: Relation[];
}

const props = defineProps<{
  note: Note | null;
}>();

const emit = defineEmits<{
  close: [];
  updated: [];
}>();

const RELATION_LABELS: Record<string, string> = {
  wikilink: "双链",
  evolved_from: "衍生自",
  supersedes: "取代",
  contradicts: "矛盾",
  related: "相关",
};

// ── 编辑模式 ──
const editingTitle = ref(false);
const editingContent = ref(false);
const editTitle = ref("");
const editContent = ref("");

function enterEditTitle() {
  if (!props.note) return;
  editTitle.value = props.note.title;
  editingTitle.value = true;
  nextTick(() => {
    (document.querySelector(".detail-title-input") as HTMLInputElement)?.focus();
  });
}

function enterEditContent() {
  if (!props.note) return;
  editContent.value = props.note.content;
  editingContent.value = true;
}

async function saveTitle() {
  if (!props.note || !editTitle.value.trim()) {
    editingTitle.value = false;
    return;
  }
  try {
    const resp = await fetch(`/notes/${props.note.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: editTitle.value.trim() }),
    });
    if (resp.ok) {
      props.note.title = editTitle.value.trim();
      emit("updated");
    }
  } catch { /* ignore */ }
  editingTitle.value = false;
}

async function saveContent() {
  if (!props.note) { editingContent.value = false; return; }
  try {
    const resp = await fetch(`/notes/${props.note.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: editContent.value }),
    });
    if (resp.ok) {
      props.note.content = editContent.value;
      emit("updated");
    }
  } catch { /* ignore */ }
  editingContent.value = false;
}

function cancelEdit() {
  editingTitle.value = false;
  editingContent.value = false;
}

// ── 关系图谱 ──
const relations = ref<RelationsData | null>(null);
const relationsLoading = ref(false);

watch(
  () => props.note?.id,
  async (id) => {
    relations.value = null;
    if (!id) return;
    relationsLoading.value = true;
    try {
      const resp = await fetch(`/notes/${id}/relations`);
      if (resp.ok) relations.value = await resp.json();
    } catch { /* ignore */ }
    relationsLoading.value = false;
  },
  { immediate: true },
);

// ── 归档 / 删除 ──
async function toggleArchive() {
  if (!props.note) return;
  const newStatus = props.note.status === "archived" ? "live" : "archived";
  try {
    const resp = await fetch(`/notes/${props.note.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    if (resp.ok) {
      props.note.status = newStatus;
      emit("updated");
    }
  } catch { /* ignore */ }
}

async function deleteNote() {
  if (!props.note || !confirm(`删除「${props.note.title}」？`)) return;
  try {
    const resp = await fetch(`/notes/${props.note.id}`, { method: "DELETE" });
    if (resp.ok) {
      emit("updated");
      emit("close");
    }
  } catch { /* ignore */ }
}

function copyContent() {
  if (!props.note) return;
  navigator.clipboard.writeText(props.note.content);
}

// ── 格式化 ──
function formatDate(s: string) {
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : `${d.getFullYear()}/${(d.getMonth() + 1).toString().padStart(2, "0")}/${d.getDate().toString().padStart(2, "0")} ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

function renderMarkdown(text: string): string {
  const raw = marked.parse(text) as string;
  return DOMPurify.sanitize(raw);
}
</script>

<template>
  <aside
    class="flex flex-col h-full border-l border-white/[0.06] bg-[#111111] overflow-hidden"
    :class="note ? 'w-72' : 'w-0'"
    style="transition: width 0.2s ease"
  >
    <template v-if="note">
      <!-- 头部 -->
      <div class="flex items-center justify-between px-4 h-12 border-b border-white/[0.06] shrink-0">
        <span class="text-[11px] font-semibold text-gray-500 tracking-[0.12em] uppercase">笔记详情</span>
        <button
          class="p-1 rounded hover:bg-white/5 text-gray-600 hover:text-gray-400 transition-colors"
          @click="emit('close')"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- 内容区 -->
      <div class="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        <!-- 标题 -->
        <div @dblclick="enterEditTitle">
          <input
            v-if="editingTitle"
            v-model="editTitle"
            class="detail-title-input w-full bg-white/[0.04] border border-white/[0.1] rounded-lg px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-indigo-500/50 transition-colors"
            @blur="saveTitle"
            @keydown.enter="saveTitle"
            @keydown.escape="cancelEdit"
          />
          <h2 v-else class="text-sm font-medium text-gray-200 leading-snug cursor-text">
            {{ note.title }}
            <span class="ml-1 text-[10px] text-gray-600 opacity-0 hover:opacity-100 transition-opacity">双击编辑</span>
          </h2>
        </div>

        <!-- 元信息 -->
        <div class="flex items-center gap-2 flex-wrap">
          <span
            :class="[
              'text-[10px] px-1.5 py-0.5 rounded-full font-medium',
              note.status === 'archived'
                ? 'bg-amber-500/10 text-amber-400 border border-amber-500/15'
                : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/15'
            ]"
          >
            {{ note.status === 'archived' ? '已归档' : '有效' }}
          </span>
          <span class="text-[10px] text-gray-600">{{ formatDate(note.created_at) }}</span>
          <span class="text-[10px] text-gray-700 font-mono">{{ note.id.slice(0, 8) }}</span>
        </div>

        <!-- 标签 -->
        <div v-if="note.tags?.length" class="flex gap-1.5 flex-wrap">
          <span
            v-for="tag in note.tags"
            :key="tag"
            class="text-[10px] px-2 py-0.5 rounded-full bg-white/[0.05] text-gray-400 border border-white/[0.04]"
          >{{ tag }}</span>
        </div>

        <!-- 正文 -->
        <div @dblclick="enterEditContent">
          <textarea
            v-if="editingContent"
            v-model="editContent"
            rows="8"
            class="w-full bg-white/[0.04] border border-white/[0.1] rounded-lg px-3 py-2 text-xs text-gray-200 leading-relaxed outline-none focus:border-indigo-500/50 transition-colors resize-y font-mono"
            @keydown.escape="cancelEdit"
          />
          <div v-if="editingContent" class="flex gap-2 mt-2">
            <button
              class="text-[11px] px-2.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
              @click="saveContent"
            >保存</button>
            <button
              class="text-[11px] px-2.5 py-1 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-gray-400 transition-colors"
              @click="cancelEdit"
            >取消</button>
          </div>
          <div
            v-else
            class="prose prose-invert prose-sm max-w-none text-xs text-gray-400 leading-relaxed whitespace-pre-wrap cursor-text"
            v-html="renderMarkdown(note.content)"
          />
        </div>

        <!-- 关系图谱 -->
        <div class="pt-3 border-t border-white/[0.06]">
          <span class="text-[10px] text-gray-600 font-medium uppercase tracking-wide">关联笔记</span>

          <div v-if="relationsLoading" class="mt-2">
            <span class="text-[10px] text-gray-700 animate-pulse">加载中…</span>
          </div>

          <template v-else-if="relations">
            <div v-if="relations.outgoing.length" class="mt-2">
              <span class="text-[10px] text-gray-600">链接到</span>
              <div class="mt-1 space-y-1">
                <div
                  v-for="rel in relations.outgoing"
                  :key="rel.id"
                  class="flex items-center gap-1.5 text-[11px] py-1"
                >
                  <svg class="w-2.5 h-2.5 text-gray-700 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                  <span class="text-gray-400 truncate">{{ rel.to_title }}</span>
                  <span class="text-[9px] px-1 rounded bg-white/[0.04] text-gray-700 shrink-0">{{ RELATION_LABELS[rel.relation] || rel.relation }}</span>
                </div>
              </div>
            </div>
            <div v-if="relations.incoming.length" class="mt-2">
              <span class="text-[10px] text-gray-600">被引用</span>
              <div class="mt-1 space-y-1">
                <div
                  v-for="rel in relations.incoming"
                  :key="rel.id"
                  class="flex items-center gap-1.5 text-[11px] py-1"
                >
                  <svg class="w-2.5 h-2.5 text-gray-700 shrink-0 rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                  <span class="text-gray-400 truncate">{{ rel.from_title }}</span>
                  <span class="text-[9px] px-1 rounded bg-white/[0.04] text-gray-700 shrink-0">{{ RELATION_LABELS[rel.relation] || rel.relation }}</span>
                </div>
              </div>
            </div>
            <p
              v-if="!relations.outgoing.length && !relations.incoming.length"
              class="mt-2 text-[10px] text-gray-700"
            >暂无关联笔记</p>
          </template>
        </div>
      </div>

      <!-- 底部操作栏 -->
      <div class="px-4 py-3 border-t border-white/[0.06] flex items-center gap-2 shrink-0">
        <button
          class="flex-1 text-[11px] px-2.5 py-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-gray-400 hover:text-gray-200 transition-colors"
          @click="copyContent"
        >复制全文</button>
        <button
          class="flex-1 text-[11px] px-2.5 py-1.5 rounded-lg transition-colors"
          :class="note.status === 'archived'
            ? 'bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400'
            : 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-400'"
          @click="toggleArchive"
        >
          {{ note.status === 'archived' ? '取消归档' : '归档' }}
        </button>
        <button
          class="text-[11px] px-2.5 py-1.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-colors"
          @click="deleteNote"
        >删除</button>
      </div>
    </template>
  </aside>
</template>
