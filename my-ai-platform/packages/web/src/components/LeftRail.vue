<script setup lang="ts">
import { ref, computed } from "vue";
import NoteListView from "../views/NoteListView.vue";
import { agentMeta, layout } from "../shared/design-tokens";

interface Note {
  id: string;
  title: string;
  content: string;
  tags: string[];
  status: string;
  created_at: string;
}

const props = defineProps<{
  open: boolean;
  selectedNoteId: string | null;
  dailyNoteCount?: number;
  dailyTrendCount?: number;
}>();

const emit = defineEmits<{
  toggle: [];
  noteSelected: [note: Note];
  toggleDigest: [];
}>();

const noteListRef = ref<InstanceType<typeof NoteListView> | null>(null);

function focusSearch() { noteListRef.value?.focusSearch(); }
function refresh() { noteListRef.value?.refresh(); }

defineExpose({ focusSearch, refresh });

const railWidth = layout.leftRailWidth;

const navItems = computed(() => [
  { id: "studio", label: "Inbox", count: props.dailyNoteCount ?? 0 },
  { id: "notes", label: "Notes" },
  { id: "daily", label: "Daily Review", badge: props.dailyTrendCount ?? 0 },
  { id: "archive", label: "Archive" },
]);

const agentItems = [
  { id: "knowledge", label: agentMeta.knowledge.label, short: agentMeta.knowledge.short },
  { id: "review", label: agentMeta.review.label, short: agentMeta.review.short },
  { id: "brain", label: agentMeta.brain.label, short: agentMeta.brain.short },
];

const activeNav = computed(() => "studio");
</script>

<template>
  <Transition name="sidebar">
    <aside
      v-show="open"
      class="studio-left-rail flex flex-col shrink-0 border-r overflow-hidden"
      :style="{ width: railWidth }"
    >
      <div class="rail-header">
        <div class="brand-mark">✦</div>
        <div class="min-w-0">
          <div class="brand-title">Thought Studio</div>
          <div class="brand-subtitle">Personal AI workspace</div>
        </div>
        <button class="collapse-btn" @click="emit('toggle')" title="收起侧边栏">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 19l-7-7 7-7" />
          </svg>
        </button>
      </div>

      <button class="new-thought-btn">
        <span>New Thought</span>
        <kbd>⌘N</kbd>
      </button>

      <nav class="rail-nav">
        <div class="section-label">Studio</div>
        <button
          v-for="item in navItems"
          :key="item.id"
          class="rail-nav-item"
          :class="{ active: activeNav === item.id }"
          @click="item.id === 'daily' ? emit('toggleDigest') : null"
        >
          <span>{{ item.label }}</span>
          <em v-if="item.count">{{ item.count }}</em>
          <i v-if="item.badge">{{ item.badge }} themes</i>
        </button>

        <div class="section-label mt-5">Agents</div>
        <div
          v-for="agent in agentItems"
          :key="agent.id"
          class="agent-pill"
        >
          <span :class="agent.id">{{ agent.short }}</span>
          <b>{{ agent.label }}</b>
        </div>
      </nav>

      <div class="note-list-wrap">
        <NoteListView
          ref="noteListRef"
          :selected-id="selectedNoteId"
          @note-selected="emit('noteSelected', $event)"
        />
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.studio-left-rail {
  background: rgba(13, 14, 20, 0.78);
  border-color: var(--border-subtle);
  backdrop-filter: blur(24px);
}

.rail-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 14px 12px;
}

.brand-mark {
  width: 32px;
  height: 32px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--brand), #B892FF);
  box-shadow: 0 14px 34px rgba(139, 124, 255, 0.28);
}

.brand-title {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 700;
}

.brand-subtitle {
  color: var(--text-tertiary);
  font-size: 10px;
  margin-top: 1px;
}

.collapse-btn {
  margin-left: auto;
  color: var(--text-tertiary);
  opacity: 0.55;
  padding: 6px;
  border-radius: 9px;
  transition: 150ms ease;
}

.collapse-btn:hover {
  opacity: 1;
  background: rgba(255,255,255,0.05);
}

.new-thought-btn {
  height: 40px;
  margin: 0 14px 16px;
  border: 1px solid var(--brand-border);
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(139,124,255,0.20), rgba(139,124,255,0.08));
  color: var(--text-primary);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  font-size: 13px;
  font-weight: 650;
}

.new-thought-btn kbd {
  color: var(--text-tertiary);
  font-size: 10px;
  font-weight: 500;
}

.rail-nav {
  padding: 0 12px 12px;
}

.section-label {
  color: var(--text-tertiary);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 0 8px 7px;
}

.rail-nav-item {
  width: 100%;
  min-height: 34px;
  border: 1px solid transparent;
  border-radius: 11px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 9px;
  font-size: 13px;
  text-align: left;
  transition: 150ms ease;
}

.rail-nav-item:hover,
.rail-nav-item.active {
  background: rgba(255,255,255,0.055);
  border-color: var(--border-subtle);
  color: var(--text-primary);
}

.rail-nav-item em,
.rail-nav-item i {
  margin-left: auto;
  color: var(--text-tertiary);
  font-style: normal;
  font-size: 11px;
}

.agent-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  margin: 0 0 7px 2px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  color: var(--text-secondary);
  background: rgba(255,255,255,0.026);
  padding: 6px 10px;
  font-size: 12px;
}

.agent-pill span {
  width: 17px;
  height: 17px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  font-size: 9px;
  font-weight: 800;
}

.agent-pill span.knowledge { color: var(--agent-knowledge); background: rgba(110,168,255,0.12); }
.agent-pill span.review { color: var(--agent-review); background: rgba(255,184,108,0.12); }
.agent-pill span.brain { color: var(--agent-brain); background: rgba(184,146,255,0.12); }
.agent-pill b { font-weight: 500; }

.note-list-wrap {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>
