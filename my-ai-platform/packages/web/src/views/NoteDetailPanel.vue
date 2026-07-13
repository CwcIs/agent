<script setup lang="ts">
import { ref, watch, nextTick, computed } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";

interface Note {
  id: string;
  title: string;
  content: string;
  tags: string[];
  status: string;
  created_at: string;
  source_url?: string;
  source_file?: string;
  source_type?: string;
  word_count?: number;
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
  similar: "相似",
  related: "相关",
};

const RELATION_COLORS: Record<string, string> = {
  wikilink: "#7C9CFF",
  evolved_from: "#70E0A3",
  supersedes: "#FFB86B",
  contradicts: "#FF6B6B",
  related: "#9AA4B2",
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

// ── Context Radar sections ──
const activeTab = ref<"referenced" | "similar" | "tensions" | "expansions">("referenced");

const tabs = [
  { id: "referenced" as const, label: "引用", icon: "↗" },
  { id: "similar" as const, label: "相似", icon: "≈" },
  { id: "tensions" as const, label: "矛盾", icon: "⚡" },
  { id: "expansions" as const, label: "联想", icon: "✦" },
];

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
    class="flex flex-col h-full overflow-hidden border-l"
    :class="note ? 'w-72' : 'w-0'"
    style="transition: width 0.2s ease; background: var(--bg-panel); border-color: var(--border-subtle)"
  >
    <template v-if="note">
      <!-- 头部 -->
      <div class="flex items-center justify-between px-4 h-11 border-b shrink-0" style="border-color: var(--border-subtle)">
        <span class="text-[10px] font-semibold uppercase tracking-[0.12em]" style="color: var(--text-muted)">Context Radar</span>
        <button
          class="p-1 rounded hover:brightness-110 transition-all"
          style="color: var(--text-muted)"
          @click="emit('close')"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Tab 切换 -->
      <div class="flex gap-0.5 px-3 py-1.5 border-b shrink-0" style="border-color: var(--border-subtle)">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="flex-1 text-[9px] py-1 rounded transition-all"
          :style="{
            background: activeTab === tab.id ? 'rgba(255,255,255,0.06)' : 'transparent',
            color: activeTab === tab.id ? 'var(--text-main)' : 'var(--text-muted)',
          }"
          @click="activeTab = tab.id"
        >
          {{ tab.icon }} {{ tab.label }}
        </button>
      </div>

      <!-- 内容区 -->
      <div class="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        <!-- 笔记基本信息（始终可见） -->
        <!-- 标题 -->
        <div @dblclick="enterEditTitle">
          <input
            v-if="editingTitle"
            v-model="editTitle"
            class="detail-title-input w-full rounded-lg px-3 py-1.5 text-sm outline-none transition-colors border"
            style="background: rgba(255,255,255,0.04); border-color: rgba(255,255,255,0.1); color: #F4F6FA"
            @blur="saveTitle"
            @keydown.enter="saveTitle"
            @keydown.escape="cancelEdit"
          />
          <h2 v-else class="text-sm font-medium leading-snug cursor-text" style="color: #F4F6FA">
            {{ note.title }}
          </h2>
        </div>

        <!-- 元信息 -->
        <div class="flex items-center gap-2 flex-wrap">
          <span
            class="text-[10px] px-1.5 py-0.5 rounded-full font-medium border"
            :style="{
              background: note.status === 'archived' ? 'rgba(255,184,107,0.08)' : 'rgba(112,224,163,0.08)',
              color: note.status === 'archived' ? '#FFB86B' : '#70E0A3',
              borderColor: note.status === 'archived' ? 'rgba(255,184,107,0.12)' : 'rgba(112,224,163,0.12)',
            }"
          >
            {{ note.status === 'archived' ? '已归档' : '有效' }}
          </span>
          <span v-if="note.source_type && note.source_type !== 'user'" class="text-[10px] px-1.5 py-0.5 rounded-full font-medium border"
            :style="{ background: 'rgba(124,156,255,0.08)', color: 'var(--agent-knowledge)', borderColor: 'rgba(124,156,255,0.12)' }">
            {{ note.source_type === 'web' ? '🌐 Web' : note.source_type === 'file' ? '📁 File' : note.source_type }}
          </span>
          <span class="text-[10px]" style="color: var(--text-muted)">{{ formatDate(note.created_at) }}</span>
          <span v-if="note.word_count" class="text-[10px]" style="color: var(--text-tertiary)">{{ note.word_count }} 字</span>
        </div>

        <!-- 来源链接 -->
        <div v-if="note.source_url" class="text-[10px] truncate">
          <a :href="note.source_url" target="_blank" class="hover:underline" style="color: var(--agent-knowledge)">🔗 {{ note.source_url }}</a>
        </div>
        <div v-else-if="note.source_file" class="text-[10px]" style="color: var(--text-muted)">
          📄 {{ note.source_file }}
        </div>

        <!-- 标签 -->
        <div v-if="note.tags?.length" class="flex gap-1.5 flex-wrap">
          <span
            v-for="tag in note.tags"
            :key="tag"
            class="text-[10px] px-2 py-0.5 rounded-full border"
            style="background: rgba(255,255,255,0.04); color: var(--text-muted); border-color: rgba(255,255,255,0.04)"
          >{{ tag }}</span>
        </div>

        <!-- ──── Tab 内容区 ──── -->

        <!-- Referenced Notes -->
        <div v-if="activeTab === 'referenced'" class="pt-2 border-t" style="border-color: var(--border-subtle)">
          <span class="text-[10px] font-medium uppercase tracking-wide" style="color: var(--text-muted)">Referenced Notes</span>
          <div v-if="relationsLoading" class="mt-2">
            <span class="text-[10px] animate-pulse" style="color: var(--text-muted)">加载中…</span>
          </div>
          <template v-else-if="relations">
            <div v-if="relations.outgoing.length" class="mt-2 space-y-1">
              <div v-for="rel in relations.outgoing" :key="rel.id" class="flex items-center gap-1.5 text-[11px] py-1">
                <svg class="w-2.5 h-2.5 shrink-0" style="color: var(--text-muted); opacity: 0.4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
                <span class="truncate" style="color: #F4F6FA">{{ rel.to_title }}</span>
                <span class="text-[9px] px-1 rounded shrink-0" style="background: rgba(255,255,255,0.04); color: var(--text-muted)">
                  {{ RELATION_LABELS[rel.relation] || rel.relation }}
                </span>
              </div>
            </div>
            <div v-if="relations.incoming.length" class="mt-2 space-y-1">
              <div v-for="rel in relations.incoming" :key="rel.id" class="flex items-center gap-1.5 text-[11px] py-1">
                <svg class="w-2.5 h-2.5 shrink-0 rotate-180" style="color: var(--text-muted); opacity: 0.4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
                <span class="truncate" style="color: #F4F6FA">{{ rel.from_title }}</span>
                <span class="text-[9px] px-1 rounded shrink-0" style="background: rgba(255,255,255,0.04); color: var(--text-muted)">
                  {{ RELATION_LABELS[rel.relation] || rel.relation }}
                </span>
              </div>
            </div>
            <p v-if="!relations.outgoing.length && !relations.incoming.length" class="mt-2 text-[10px]" style="color: var(--text-muted)">
              暂无关联笔记
            </p>
          </template>
        </div>

        <!-- Similar Ideas -->
        <div v-if="activeTab === 'similar'" class="pt-2 border-t" style="border-color: var(--border-subtle)">
          <span class="text-[10px] font-medium uppercase tracking-wide" style="color: var(--text-muted)">Similar Ideas</span>
          <p class="mt-2 text-[10px]" style="color: var(--text-muted); opacity: 0.5">
            选择一条消息后，向量检索会在此显示相似笔记
          </p>
        </div>

        <!-- Tensions -->
        <div v-if="activeTab === 'tensions'" class="pt-2 border-t" style="border-color: var(--border-subtle)">
          <span class="text-[10px] font-medium uppercase tracking-wide" style="color: var(--text-muted)">Tensions</span>
          <p class="mt-2 text-[10px]" style="color: var(--text-muted); opacity: 0.5">
            ReviewAgent 发现的矛盾或盲点会在此显示
          </p>
        </div>

        <!-- Expansions -->
        <div v-if="activeTab === 'expansions'" class="pt-2 border-t" style="border-color: var(--border-subtle)">
          <span class="text-[10px] font-medium uppercase tracking-wide" style="color: var(--text-muted)">Expansions</span>
          <p class="mt-2 text-[10px]" style="color: var(--text-muted); opacity: 0.5">
            BrainAgent 的联想方向会在此显示
          </p>
        </div>

        <!-- 正文（始终可访问） -->
        <div class="pt-2 border-t" style="border-color: var(--border-subtle)" @dblclick="enterEditContent">
          <span class="text-[10px] font-medium uppercase tracking-wide" style="color: var(--text-muted)">内容</span>
          <textarea
            v-if="editingContent"
            v-model="editContent"
            rows="6"
            class="w-full rounded-lg px-3 py-2 text-xs leading-relaxed outline-none transition-colors resize-y font-mono mt-2 border"
            style="background: rgba(255,255,255,0.04); border-color: rgba(255,255,255,0.1); color: #F4F6FA"
            @keydown.escape="cancelEdit"
          />
          <div v-if="editingContent" class="flex gap-2 mt-2">
            <button
              class="text-[11px] px-2.5 py-1 rounded-lg transition-colors text-white"
              style="background: var(--agent-knowledge)"
              @click="saveContent"
            >保存</button>
            <button
              class="text-[11px] px-2.5 py-1 rounded-lg transition-colors border"
              style="background: rgba(255,255,255,0.04); color: var(--text-muted); border-color: rgba(255,255,255,0.08)"
              @click="cancelEdit"
            >取消</button>
          </div>
          <div
            v-else
            class="prose prose-invert prose-sm max-w-none text-xs leading-relaxed whitespace-pre-wrap cursor-text mt-2"
            style="color: var(--text-muted)"
            v-html="renderMarkdown(note.content)"
          />
        </div>
      </div>

      <!-- 底部操作栏 -->
      <div class="px-4 py-3 border-t flex items-center gap-2 shrink-0" style="border-color: var(--border-subtle)">
        <button
          class="flex-1 text-[11px] px-2.5 py-1.5 rounded-lg transition-all hover:brightness-110 border"
          style="background: rgba(255,255,255,0.04); color: var(--text-muted); border-color: rgba(255,255,255,0.06)"
          @click="copyContent"
        >复制</button>
        <button
          class="flex-1 text-[11px] px-2.5 py-1.5 rounded-lg transition-all hover:brightness-110 border"
          :style="{
            background: note.status === 'archived' ? 'rgba(112,224,163,0.08)' : 'rgba(255,184,107,0.08)',
            color: note.status === 'archived' ? '#70E0A3' : '#FFB86B',
            borderColor: note.status === 'archived' ? 'rgba(112,224,163,0.12)' : 'rgba(255,184,107,0.12)',
          }"
          @click="toggleArchive"
        >
          {{ note.status === 'archived' ? '恢复' : '归档' }}
        </button>
        <button
          class="text-[11px] px-2.5 py-1.5 rounded-lg transition-all hover:brightness-110 border"
          style="background: rgba(255,107,107,0.08); color: #FF6B6B; border-color: rgba(255,107,107,0.12)"
          @click="deleteNote"
        >删除</button>
      </div>
    </template>
  </aside>
</template>
