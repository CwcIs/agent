<script setup lang="ts">
import { ref, computed } from "vue";
import NoteListView from "../views/NoteListView.vue";
import { agentMeta, colors, layout } from "../shared/design-tokens";

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

// ── Navigation Items ──
const navItems = [
  { id: 'studio',     icon: '◆', label: 'Studio' },
  { id: 'notes',      icon: '▦', label: 'Notes',     count: 0 },
  { id: 'daily',      icon: '◉', label: 'Daily Review', badge: props.dailyTrendCount },
  { id: 'archive',    icon: '◻', label: 'Archive' },
];

const agentItems = [
  { id: 'knowledge', label: agentMeta.knowledge.label, short: agentMeta.knowledge.short },
  { id: 'review',    label: agentMeta.review.label,    short: agentMeta.review.short },
  { id: 'brain',     label: agentMeta.brain.label,     short: agentMeta.brain.short },
];

const activeNav = computed(() => 'studio');
</script>

<template>
  <Transition name="sidebar">
    <aside
      v-show="open"
      class="flex flex-col shrink-0 border-r overflow-hidden"
      :style="{ width: railWidth, background: 'var(--surface-base)', borderColor: 'var(--border-subtle)' }"
    >
      <!-- Header -->
      <div
        class="flex items-center justify-between px-4 h-11 shrink-0 border-b"
        :style="{ borderColor: 'var(--border-subtle)' }"
      >
        <span
          class="text-[11px] font-semibold tracking-[0.08em]"
          :style="{ color: 'var(--text-secondary)' }"
        >AI Thought Studio</span>
        <button
          class="p-1 rounded hover:brightness-125 transition-all opacity-40 hover:opacity-70"
          :style="{ color: 'var(--text-secondary)' }"
          @click="emit('toggle')"
          title="收起侧边栏"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 19l-7-7 7-7" />
          </svg>
        </button>
      </div>

      <!-- Navigation -->
      <nav class="px-3 py-3 space-y-0.5 shrink-0">
        <div class="text-[10px] font-medium uppercase tracking-[0.1em] px-1.5 mb-2" :style="{ color: 'var(--text-tertiary)' }">
          Spaces
        </div>
        <button
          v-for="item in navItems"
          :key="item.id"
          class="w-full flex items-center gap-2.5 px-2 py-1.5 rounded-[8px] text-[13px] transition-all text-left"
          :class="activeNav === item.id ? '' : 'opacity-50 hover:opacity-75'"
          :style="{
            color: activeNav === item.id ? 'var(--text-primary)' : 'var(--text-secondary)',
            background: activeNav === item.id ? 'var(--surface-hover)' : 'transparent',
          }"
          @click="item.id === 'daily' ? emit('toggleDigest') : null"
        >
          <span class="text-[10px] w-4 text-center shrink-0" :style="{ opacity: 0.6 }">{{ item.icon }}</span>
          <span class="flex-1">{{ item.label }}</span>
          <span
            v-if="item.badge && item.badge > 0"
            class="text-[9px] px-1.5 py-px rounded-full font-medium shrink-0"
            :style="{ background: 'var(--brand-soft)', color: 'var(--brand)' }"
          >{{ item.badge }}</span>
        </button>

        <!-- Agents section -->
        <div class="text-[10px] font-medium uppercase tracking-[0.1em] px-1.5 mt-4 mb-2" :style="{ color: 'var(--text-tertiary)' }">
          Agents
        </div>
        <div
          v-for="agent in agentItems"
          :key="agent.id"
          class="flex items-center gap-2.5 px-2 py-1.5 text-[13px] opacity-50"
          :style="{ color: 'var(--text-secondary)' }"
        >
          <span
            class="w-4 h-4 rounded-[4px] flex items-center justify-center text-[8px] font-bold shrink-0"
            :style="{
              background: `var(--agent-${agent.id})` + '15',
              color: `var(--agent-${agent.id})`,
            }"
          >{{ agent.short }}</span>
          <span>{{ agent.label }}</span>
        </div>
      </nav>

      <!-- Note List -->
      <div class="flex-1 min-h-0 overflow-hidden">
        <NoteListView
          ref="noteListRef"
          :selected-id="selectedNoteId"
          @note-selected="emit('noteSelected', $event)"
        />
      </div>
    </aside>
  </Transition>
</template>
