<script setup lang="ts">
import { ref, computed, onMounted } from "vue";

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

const notes = ref<Note[]>([]);
const filter = ref<"live" | "archived" | "all">("live");
const loading = ref(false);
const expandedId = ref<string | null>(null);
const relationsCache = ref<Record<string, RelationsData>>({});
const relationsLoading = ref<Record<string, boolean>>({});

const RELATION_LABELS: Record<string, string> = {
  wikilink: "双链",
  evolved_from: "衍生自",
  supersedes: "取代",
  contradicts: "矛盾",
  related: "相关",
};

const filtered = computed(() =>
  filter.value === "all" ? notes.value : notes.value.filter((n) => n.status === filter.value)
);

const statusLabels: Record<string, string> = {
  live: "有效",
  archived: "归档",
  all: "全部",
};

async function fetchNotes() {
  try {
    const resp = await fetch("/notes");
    const data = await resp.json();
    notes.value = data.notes ?? [];
  } catch {
    notes.value = [];
  }
}

onMounted(fetchNotes);

defineExpose({ refresh: fetchNotes });

function formatDate(s: string) {
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : `${d.getMonth() + 1}/${d.getDate()}`;
}

async function archiveNote(note: Note) {
  const prevStatus = note.status;
  const newStatus = prevStatus === "archived" ? "live" : "archived";
  note.status = newStatus;
  try {
    const resp = await fetch(`/notes/${note.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  } catch {
    note.status = prevStatus; // 回滚
  }
}

async function deleteNote(note: Note) {
  if (!confirm(`删除「${note.title}」？`)) return;
  const prevNotes = notes.value;
  notes.value = notes.value.filter((n) => n.id !== note.id);
  try {
    const resp = await fetch(`/notes/${note.id}`, { method: "DELETE" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  } catch {
    notes.value = prevNotes; // 回滚
  }
}

function toggleExpand(noteId: string) {
  if (expandedId.value === noteId) {
    expandedId.value = null;
    return;
  }
  expandedId.value = noteId;
  // 懒加载关系图谱
  if (!relationsCache.value[noteId] && !relationsLoading.value[noteId]) {
    fetchRelations(noteId);
  }
}

async function fetchRelations(noteId: string) {
  relationsLoading.value[noteId] = true;
  try {
    const resp = await fetch(`/notes/${noteId}/relations`);
    if (resp.ok) {
      relationsCache.value[noteId] = await resp.json();
    }
  } catch {
    // ignore
  } finally {
    relationsLoading.value[noteId] = false;
  }
}
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- 过滤标签 -->
    <div class="flex gap-1 px-3 pt-3 pb-2">
      <button
        v-for="s in (['live', 'archived', 'all'] as const)"
        :key="s"
        :class="[
          'px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors',
          filter === s ? 'bg-white/10 text-gray-200' : 'text-gray-600 hover:text-gray-400'
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
        class="group px-3 py-2.5 rounded-lg hover:bg-white/[0.04] transition-colors cursor-pointer"
        :class="{ 'opacity-40': note.status === 'archived' }"
        @click="toggleExpand(note.id)"
      >
        <div class="flex items-start justify-between gap-1">
          <span class="text-sm text-gray-300 leading-snug flex-1">{{ note.title }}</span>

          <!-- 操作按钮 hover 才显示 -->
          <div class="flex gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" @click.stop>
            <!-- 归档 / 取消归档 -->
            <button
              class="p-1 rounded hover:bg-white/10 transition-colors"
              :title="note.status === 'archived' ? '取消归档' : '归档'"
              @click.stop="archiveNote(note)"
            >
              <svg class="w-3 h-3 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8l1 12a2 2 0 002 2h8a2 2 0 002-2L19 8" />
              </svg>
            </button>
            <!-- 删除 -->
            <button
              class="p-1 rounded hover:bg-red-500/20 transition-colors"
              title="删除"
              @click.stop="deleteNote(note)"
            >
              <svg class="w-3 h-3 text-gray-500 hover:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>

          <span class="text-[10px] text-gray-700 shrink-0 mt-0.5 group-hover:hidden">{{ formatDate(note.created_at) }}</span>
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

        <!-- 展开内容 -->
        <div
          v-if="expandedId === note.id"
          class="mt-2.5 pt-2.5 border-t border-white/[0.06]"
          @click.stop
        >
          <p class="text-xs text-gray-400 leading-relaxed whitespace-pre-wrap">{{ note.content }}</p>
          <div class="flex items-center gap-3 mt-2 text-[10px] text-gray-600">
            <span>创建于 {{ formatDate(note.created_at) }}</span>
            <span class="text-gray-700">{{ note.id.slice(0, 8) }}</span>
          </div>

          <!-- 相关笔记（关系图谱） -->
          <div
            v-if="relationsCache[note.id]"
            class="mt-2.5 pt-2.5 border-t border-white/[0.06]"
          >
            <template v-if="relationsCache[note.id].outgoing.length || relationsCache[note.id].incoming.length">
              <!-- 出链 -->
              <div v-if="relationsCache[note.id].outgoing.length" class="mb-2">
                <span class="text-[10px] text-gray-600 font-medium">链接到</span>
                <div class="mt-1 space-y-1">
                  <div
                    v-for="rel in relationsCache[note.id].outgoing"
                    :key="rel.id"
                    class="flex items-center gap-1.5 text-[11px]"
                  >
                    <span class="text-gray-500 truncate max-w-[140px]">{{ rel.to_title }}</span>
                    <span class="text-[10px] px-1 rounded bg-white/[0.04] text-gray-700 shrink-0">{{ RELATION_LABELS[rel.relation] || rel.relation }}</span>
                  </div>
                </div>
              </div>
              <!-- 入链 -->
              <div v-if="relationsCache[note.id].incoming.length">
                <span class="text-[10px] text-gray-600 font-medium">被引用</span>
                <div class="mt-1 space-y-1">
                  <div
                    v-for="rel in relationsCache[note.id].incoming"
                    :key="rel.id"
                    class="flex items-center gap-1.5 text-[11px]"
                  >
                    <span class="text-gray-500 truncate max-w-[140px]">{{ rel.from_title }}</span>
                    <span class="text-[10px] px-1 rounded bg-white/[0.04] text-gray-700 shrink-0">{{ RELATION_LABELS[rel.relation] || rel.relation }}</span>
                  </div>
                </div>
              </div>
            </template>
            <p v-else class="text-[10px] text-gray-700">暂无关联笔记</p>
          </div>
          <div v-else-if="relationsLoading[note.id]" class="mt-2.5 pt-2.5 border-t border-white/[0.06]">
            <span class="text-[10px] text-gray-700 animate-pulse">加载关联…</span>
          </div>
        </div>
      </li>
    </ul>

    <div v-if="!filtered.length" class="px-4 py-6 text-center">
      <p class="text-xs text-gray-700">还没有笔记</p>
    </div>
  </div>
</template>
