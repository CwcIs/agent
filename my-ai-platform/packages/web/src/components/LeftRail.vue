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

const navItems = computed(() => [
  { id: "inbox", label: "Inbox", count: props.dailyNoteCount ?? 0 },
  { id: "notes", label: "Notes" },
  { id: "daily", label: "Daily Review", badge: props.dailyTrendCount ?? 0 },
  { id: "archive", label: "Archive" },
]);

const agentItems = [
  { id: "knowledge", label: agentMeta.knowledge.label, short: agentMeta.knowledge.short, role: agentMeta.knowledge.role },
  { id: "review", label: agentMeta.review.label, short: agentMeta.review.short, role: agentMeta.review.role },
  { id: "brain", label: agentMeta.brain.label, short: agentMeta.brain.short, role: agentMeta.brain.role },
];
</script>

<template>
  <Transition name="sidebar">
    <aside v-show="open" class="left-rail" :style="{ width: layout.leftRailWidth }">
      <div class="brand-row">
        <div class="brand-mark">✦</div>
        <div class="brand-copy">
          <strong>Thought Studio</strong>
          <span>AI knowledge workspace</span>
        </div>
        <button class="ghost-icon" title="收起侧边栏" @click="emit('toggle')">‹</button>
      </div>

      <button class="primary-create">
        <span>New thought</span>
        <kbd>⌘N</kbd>
      </button>

      <nav class="nav-section">
        <p class="section-title">Workspace</p>
        <button
          v-for="item in navItems"
          :key="item.id"
          class="nav-item"
          :class="{ active: item.id === 'inbox' }"
          @click="item.id === 'daily' ? emit('toggleDigest') : null"
        >
          <span>{{ item.label }}</span>
          <em v-if="item.count">{{ item.count }}</em>
          <i v-if="item.badge">{{ item.badge }} themes</i>
        </button>
      </nav>

      <section class="nav-section">
        <p class="section-title">Agents</p>
        <div v-for="agent in agentItems" :key="agent.id" class="agent-card">
          <span class="agent-avatar" :class="agent.id">{{ agent.short }}</span>
          <div>
            <strong>{{ agent.label }}</strong>
            <small>{{ agent.role }}</small>
          </div>
        </div>
      </section>

      <section class="notes-panel">
        <div class="notes-panel-head">
          <p class="section-title">Memory</p>
          <span>Live</span>
        </div>
        <NoteListView
          ref="noteListRef"
          :selected-id="selectedNoteId"
          @note-selected="emit('noteSelected', $event)"
        />
      </section>
    </aside>
  </Transition>
</template>

<style scoped>
.left-rail {
  position: relative;
  z-index: 2;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px 12px;
  border-right: 1px solid var(--border-subtle);
  background: rgba(9, 10, 15, 0.72);
  backdrop-filter: blur(26px);
}

.brand-row {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 2px 4px;
}

.brand-mark {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  background: linear-gradient(135deg, var(--brand), var(--brand-2));
  box-shadow: 0 18px 42px rgba(154, 134, 255, 0.28);
  color: white;
}

.brand-copy { min-width: 0; display: grid; gap: 1px; }
.brand-copy strong { font-size: 14px; letter-spacing: -0.02em; color: var(--text-primary); }
.brand-copy span { font-size: 10.5px; color: var(--text-tertiary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.ghost-icon {
  margin-left: auto;
  width: 28px;
  height: 28px;
  border-radius: 10px;
  color: var(--text-tertiary);
  transition: 160ms ease;
}
.ghost-icon:hover { color: var(--text-primary); background: rgba(255,255,255,0.06); }

.primary-create {
  height: 44px;
  border: 1px solid var(--brand-border);
  border-radius: 16px;
  padding: 0 13px;
  color: white;
  background: linear-gradient(135deg, rgba(154,134,255,0.30), rgba(154,134,255,0.10));
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.10);
}
.primary-create span { font-size: 13px; font-weight: 700; }
.primary-create kbd { color: var(--text-tertiary); font-size: 10px; }

.nav-section { display: grid; gap: 6px; }
.section-title {
  margin: 0;
  padding: 0 8px 2px;
  color: var(--text-tertiary);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.13em;
  text-transform: uppercase;
}

.nav-item {
  min-height: 36px;
  border: 1px solid transparent;
  border-radius: 12px;
  padding: 0 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 13px;
  text-align: left;
  transition: 160ms ease;
}
.nav-item:hover, .nav-item.active { background: rgba(255,255,255,0.06); border-color: var(--border-subtle); color: var(--text-primary); }
.nav-item em, .nav-item i { margin-left: auto; font-style: normal; color: var(--text-tertiary); font-size: 11px; }

.agent-card {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 15px;
  padding: 10px;
  background: rgba(255,255,255,0.032);
}
.agent-avatar { width: 25px; height: 25px; border-radius: 10px; display: grid; place-items: center; font-size: 11px; font-weight: 850; }
.agent-avatar.knowledge { color: var(--agent-knowledge); background: rgba(121,174,255,0.12); }
.agent-avatar.review { color: var(--agent-review); background: rgba(255,189,115,0.12); }
.agent-avatar.brain { color: var(--agent-brain); background: rgba(196,154,255,0.12); }
.agent-card strong { display: block; color: var(--text-primary); font-size: 12px; }
.agent-card small { display: block; color: var(--text-tertiary); font-size: 10.5px; margin-top: 1px; line-height: 1.35; }

.notes-panel {
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-subtle);
  border-radius: 18px;
  background: rgba(255,255,255,0.025);
  overflow: hidden;
}
.notes-panel-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 10px 8px; }
.notes-panel-head span { color: var(--color-success); font-size: 10px; }
</style>
