<script setup lang="ts">
/**
 * ThoughtComposer — 浮动胶囊输入区（替代 QuickCaptureBar）。
 *
 * 设计要点：
 * - 浮动卡片，圆角 composer (22px)
 * - 智能建议：根据输入内容启发式推荐动作
 * - / 命令面板 + #tag 检测
 * - 与 QuickCaptureBar 相同的 defineModel + emit 接口
 */
import { computed } from "vue";
import { agentColors, colors, radii } from "../shared/design-tokens";

const input = defineModel<string>("input", { default: "" });
const streaming = defineModel<boolean>("streaming", { default: false });

const emit = defineEmits<{
  send: [];
  abort: [];
  insertCommand: [cmd: string];
}>();

// ── Commands ──
const COMMANDS = [
  { trigger: "/review", label: "Review Agent", desc: "审视你的想法", agentKey: "review" as const },
  { trigger: "/brain", label: "Brain Agent", desc: "联想扩展", agentKey: "brain" as const },
];

const showCommands = computed(() => input.value.startsWith("/") && !input.value.includes(" "));

// ── Tag detection ──
const activeTag = computed(() => {
  const m = input.value.match(/#([a-zA-Z][a-zA-Z0-9_-]*)/);
  if (!m) return null;
  const tag = m[1].toLowerCase();
  const map: Record<string, string> = { review: "Review Agent", brain: "Brain Agent" };
  if (tag in map) return { tag, label: map[tag] };
  return null;
});

// ── Smart Suggestions ──
interface Suggestion {
  id: string;
  label: string;
  icon: string;
  color: string;
}

const suggestions = computed<Suggestion[]>(() => {
  const text = input.value.trim();
  if (!text || text.startsWith("/") || text.startsWith("#")) return [];

  const items: Suggestion[] = [];

  // Short fragment → suggest saving
  if (text.length < 80) {
    items.push({ id: 'save', label: '保存为笔记', icon: '▦', color: 'var(--color-success)' });
  }

  // Judgment/opinion keywords → suggest Review
  if (/是否|应该|认为|判断|假设|可能|不一定|不一定对/.test(text)) {
    items.push({ id: 'review', label: '让 Review 挑战', icon: '⚠', color: 'var(--agent-review)' });
  }

  // Concept/inspiration keywords → suggest Brain
  if (/想法|灵感|概念|跨界|联想|可能|如果|设想/.test(text)) {
    items.push({ id: 'brain', label: '让 Brain 发散', icon: '◇', color: 'var(--agent-brain)' });
  }

  return items.slice(0, 3);
});

function handleSuggestion(s: Suggestion) {
  switch (s.id) {
    case 'save': input.value = "#save " + input.value; break;
    case 'review': input.value = "#review " + input.value; break;
    case 'brain': input.value = "#brain " + input.value; break;
  }
  emit('send');
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    emit("send");
  }
}

function handleInput(e: Event) {
  const el = e.target as HTMLTextAreaElement;
  el.style.height = "auto";
  el.style.height = el.scrollHeight + "px";
}
</script>

<template>
  <div class="px-4 pb-4 shrink-0 relative">
    <!-- Smart Suggestions -->
    <div
      v-if="suggestions.length && !streaming"
      class="flex items-center gap-2 mb-2 px-1"
    >
      <span class="text-[10px] shrink-0" :style="{ color: 'var(--text-tertiary)' }">建议：</span>
      <button
        v-for="s in suggestions"
        :key="s.id"
        class="text-[10px] px-2 py-0.5 rounded-full border transition-all hover:brightness-110"
        :style="{
          color: s.color,
          background: s.color + '10',
          borderColor: s.color + '20',
        }"
        @click="handleSuggestion(s)"
      >
        {{ s.icon }} {{ s.label }}
      </button>
    </div>

    <!-- / Command Panel -->
    <div
      v-if="showCommands && input.length >= 1"
      class="absolute bottom-full left-4 right-4 mb-2 rounded-xl shadow-2xl overflow-hidden z-10 border"
      :style="{ background: 'var(--surface-raised)', borderColor: 'var(--border-subtle)' }"
    >
      <div class="px-3 py-1.5 text-[10px] border-b" :style="{ color: 'var(--text-tertiary)', borderColor: 'var(--border-subtle)' }">
        命令
      </div>
      <button
        v-for="cmd in COMMANDS"
        :key="cmd.trigger"
        class="w-full flex items-center gap-2.5 px-3 py-2 text-left transition-all"
        :class="input === cmd.trigger ? 'opacity-100' : 'opacity-60'"
        :style="{ background: input === cmd.trigger ? 'var(--surface-hover)' : 'transparent' }"
        @click="emit('insertCommand', cmd.trigger)"
      >
        <span
          class="w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold shrink-0"
          :style="{
            background: agentColors[cmd.agentKey].bg,
            color: agentColors[cmd.agentKey].hex,
          }"
        >/</span>
        <div>
          <span class="text-xs" :style="{ color: 'var(--text-primary)' }">{{ cmd.trigger }}</span>
          <span class="text-[10px] ml-1.5" :style="{ color: 'var(--text-tertiary)' }">{{ cmd.desc }}</span>
        </div>
      </button>
    </div>

    <!-- Tag pill -->
    <div v-if="activeTag" class="mb-1.5 flex items-center gap-1.5 px-1">
      <span class="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full border" :style="{
        background: 'var(--brand-soft)',
        color: 'var(--brand)',
        borderColor: 'var(--brand-border)',
      }">
        <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
        → {{ activeTag.label }}
      </span>
    </div>

    <!-- Composer Card -->
    <div
      class="border transition-all"
      :class="[
        activeTag ? '' : '',
        showCommands ? '' : '',
      ]"
      :style="{
        borderRadius: radii.composer,
        background: 'var(--surface-raised)',
        borderColor: activeTag ? 'var(--brand-border)' : 'var(--border-subtle)',
        boxShadow: activeTag ? '0 0 0 1px var(--brand-border)' : 'none',
      }"
    >
      <textarea
        v-model="input"
        class="chat-input w-full bg-transparent text-[15px] leading-relaxed outline-none resize-none px-4 py-3"
        :style="{
          color: 'var(--text-primary)',
          minHeight: '48px',
          maxHeight: '160px',
        }"
        :placeholder="activeTag ? `#${activeTag.tag} 已激活…` : '写下一个想法、问题或碎片……'"
        rows="1"
        @keydown="handleKeydown"
        @input="handleInput"
      />

      <!-- Bottom actions row -->
      <div class="flex items-center gap-1 px-2 pb-2">
        <!-- Quick action buttons -->
        <button
          class="text-[10px] px-2 py-1 rounded-md transition-all hover:brightness-110 opacity-50 hover:opacity-80"
          :style="{ color: 'var(--text-tertiary)' }"
          @click="emit('insertCommand', '/review')"
          title="Review 挑战"
        >+ Review</button>
        <button
          class="text-[10px] px-2 py-1 rounded-md transition-all hover:brightness-110 opacity-50 hover:opacity-80"
          :style="{ color: 'var(--text-tertiary)' }"
          @click="emit('insertCommand', '/brain')"
          title="Brain 联想"
        >+ Brain</button>

        <div class="flex-1" />

        <!-- Send / Abort button -->
        <button
          v-if="!streaming"
          class="w-8 h-8 rounded-full flex items-center justify-center transition-all hover:brightness-110"
          :class="input.trim() ? '' : 'opacity-30'"
          :style="{ background: input.trim() ? 'var(--brand)' : 'var(--surface-hover)' }"
          :disabled="!input.trim()"
          @click="emit('send')"
        >
          <svg class="w-4 h-4" fill="none" stroke="#fff" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </button>
        <button
          v-else
          class="w-8 h-8 rounded-full flex items-center justify-center transition-all hover:brightness-110"
          :style="{ background: 'var(--color-danger)' }"
          @click="emit('abort')"
        >
          <svg class="w-3.5 h-3.5" fill="#fff" viewBox="0 0 24 24">
            <rect x="4" y="4" width="16" height="16" rx="2" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>
