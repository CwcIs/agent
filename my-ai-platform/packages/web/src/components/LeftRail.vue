<script setup lang="ts">
import { computed, ref } from "vue";
import NoteListView from "../views/NoteListView.vue";
import { agentMeta, layout } from "../shared/design-tokens";
import type { ChatThread } from "../composables/useChatThreads";

interface Note {
  id: string;
  title: string;
  content: string;
  tags: string[];
  status: string;
  knowledge_status?: string;
  created_at: string;
}

const props = defineProps<{
  open: boolean;
  selectedNoteId: string | null;
  dailyNoteCount?: number;
  dailyTrendCount?: number;
  threads: ChatThread[];
  activeSessionId: string;
  loadingThreads?: boolean;
}>();

const emit = defineEmits<{
  toggle: [];
  noteSelected: [note: Note];
  toggleDigest: [];
  newThread: [];
  selectThread: [sessionId: string];
  openHub: [];
}>();

const noteListRef = ref<InstanceType<typeof NoteListView> | null>(null);
const visibleThreads = computed(() => props.threads.slice(0, 8));

function focusSearch() { noteListRef.value?.focusSearch(); }
function refresh() { noteListRef.value?.refresh(); }
defineExpose({ focusSearch, refresh });

function formatThreadTime(value: string): string {
  if (!value) return "";
  const date = new Date(value.replace(" ", "T"));
  const today = new Date();
  if (date.toDateString() === today.toDateString()) {
    return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  }
  return `${date.getMonth() + 1}/${date.getDate()}`;
}
</script>

<template>
  <Transition name="sidebar">
    <aside v-show="open" class="left-rail" :style="{ width: layout.leftRailWidth }">
      <div class="brand-row">
        <div class="brand-mark">TS</div>
        <div class="brand-copy">
          <strong>Thought Studio</strong>
          <span>Personal knowledge team</span>
        </div>
        <button class="ghost-icon" title="收起侧边栏" aria-label="收起侧边栏" @click="emit('toggle')">‹</button>
      </div>

      <button class="primary-create" @click="emit('newThread')">
        <span class="plus">+</span>
        <span>新建思考任务</span>
      </button>

      <section class="thread-section">
        <div class="section-head">
          <p class="section-title">Tasks</p>
          <span v-if="loadingThreads">同步中</span>
          <span v-else>{{ threads.length }}</span>
        </div>
        <div class="thread-list">
          <button
            v-for="thread in visibleThreads"
            :key="thread.session_id"
            class="thread-item"
            :class="{ active: thread.session_id === activeSessionId }"
            @click="emit('selectThread', thread.session_id)"
          >
            <span class="thread-marker" />
            <span class="thread-copy">
              <strong>{{ thread.title }}</strong>
              <small>{{ thread.message_count }} 条消息 · {{ formatThreadTime(thread.updated_at) }}</small>
            </span>
            <span class="agent-stack">
              <i
                v-for="agentId in thread.agent_ids.slice(0, 3)"
                :key="agentId"
                :class="agentId"
                :title="agentMeta[agentId]?.label || agentId"
              >{{ agentMeta[agentId]?.short || agentId.slice(0, 1).toUpperCase() }}</i>
            </span>
          </button>
          <div v-if="!loadingThreads && !threads.length" class="thread-empty">
            新任务会在发送第一条消息后出现在这里
          </div>
        </div>
      </section>

      <div class="workspace-actions">
        <button @click="emit('openHub')"><b>H</b><span>Workbench Hub</span><i>›</i></button>
        <button @click="emit('toggleDigest')">
          <b>D</b><span>Daily Review</span><em v-if="dailyTrendCount">{{ dailyTrendCount }}</em>
        </button>
      </div>

      <section class="notes-panel">
        <div class="notes-panel-head">
          <p class="section-title">Knowledge</p>
          <span>{{ dailyNoteCount ?? 0 }} today</span>
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
  gap: 12px;
  padding: 14px 10px;
  border-right: 1px solid var(--border-subtle);
  background: #0b0f13;
}
.brand-row { display: flex; align-items: center; gap: 10px; padding: 2px 3px; }
.brand-mark {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 1px solid #31515c;
  border-radius: 6px;
  background: #17272d;
  color: #a8dce6;
  font-size: 10px;
  font-weight: 850;
}
.brand-copy { min-width: 0; display: grid; gap: 1px; }
.brand-copy strong { color: var(--text-primary); font-size: 14px; }
.brand-copy span { overflow: hidden; color: var(--text-tertiary); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.ghost-icon {
  width: 28px;
  height: 28px;
  margin-left: auto;
  border-radius: 6px;
  color: var(--text-tertiary);
  font-size: 18px;
}
.ghost-icon:hover { color: var(--text-primary); background: var(--surface-hover); }
.primary-create {
  height: 38px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 10px;
  border: 1px solid #31515c;
  border-radius: 6px;
  background: #16242a;
  color: #d9eef2;
}
.primary-create span { font-size: 13px; font-weight: 700; }
.primary-create .plus { font-size: 18px; font-weight: 400; }
.primary-create:hover { background: #1b3038; border-color: #49717f; }
.section-head { display: flex; align-items: center; justify-content: space-between; }
.section-head > span { padding-right: 7px; color: var(--text-tertiary); font-size: 10px; }
.section-title {
  margin: 0;
  padding: 0 7px 2px;
  color: var(--text-tertiary);
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}
.thread-section { min-height: 104px; }
.thread-list { display: grid; gap: 2px; max-height: 220px; margin-top: 3px; overflow-y: auto; }
.thread-item {
  width: 100%;
  min-height: 47px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 7px;
  border: 1px solid transparent;
  border-radius: 6px;
  color: var(--text-secondary);
  text-align: left;
}
.thread-item:hover { background: var(--surface-hover); }
.thread-item.active { background: #151c22; border-color: #29353f; }
.thread-marker { width: 3px; height: 24px; flex: 0 0 3px; border-radius: 2px; background: transparent; }
.thread-item.active .thread-marker { background: #7bc3d4; }
.thread-copy { min-width: 0; flex: 1; display: grid; gap: 3px; }
.thread-copy strong { overflow: hidden; color: var(--text-secondary); font-size: 11px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.thread-item.active .thread-copy strong { color: var(--text-primary); }
.thread-copy small { color: var(--text-tertiary); font-size: 9px; }
.agent-stack { display: flex; }
.agent-stack i {
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  margin-left: -4px;
  border: 2px solid #0b0f13;
  border-radius: 50%;
  background: #202832;
  color: var(--text-tertiary);
  font-size: 7px;
  font-style: normal;
}
.agent-stack i.knowledge { color: var(--agent-knowledge); }
.agent-stack i.review { color: var(--agent-review); }
.agent-stack i.brain { color: var(--agent-brain); }
.thread-empty { padding: 10px 8px; color: var(--text-tertiary); font-size: 10px; line-height: 1.5; }
.workspace-actions { display: grid; gap: 2px; padding: 7px 0; border-top: 1px solid var(--border-subtle); border-bottom: 1px solid var(--border-subtle); }
.workspace-actions button {
  min-height: 34px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 8px;
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 11px;
  text-align: left;
}
.workspace-actions button:hover { background: var(--surface-hover); color: var(--text-primary); }
.workspace-actions b { width: 22px; height: 22px; display: grid; place-items: center; border-radius: 5px; background: #1b252d; color: #9ccfe0; font-size: 8px; }
.workspace-actions i, .workspace-actions em { margin-left: auto; color: var(--text-tertiary); font-style: normal; }
.workspace-actions em { min-width: 17px; height: 17px; display: grid; place-items: center; border-radius: 50%; background: rgba(255,196,112,.12); color: var(--color-warning); font-size: 8px; }
.notes-panel {
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-top: 1px solid var(--border-subtle);
}
.notes-panel-head { display: flex; align-items: center; justify-content: space-between; padding: 10px 3px 6px; }
.notes-panel-head span { color: var(--text-tertiary); font-size: 9px; }
@media (max-width: 759px) {
  .left-rail {
    position: absolute;
    inset: 0 auto 0 0;
    width: min(86vw, 300px) !important;
    height: 100%;
    box-shadow: 18px 0 50px rgba(0, 0, 0, .48);
  }
}
</style>
