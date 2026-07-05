<script setup lang="ts">
import { computed } from "vue";

const input = defineModel<string>("input", { default: "" });
const streaming = defineModel<boolean>("streaming", { default: false });

const emit = defineEmits<{
  send: [];
  abort: [];
  insertCommand: [cmd: string];
}>();

// Direct hex colors for JS inline styles
const CMD_COLORS: Record<string, { hex: string; bg: string }> = {
  review: { hex: "#FFB86B", bg: "rgba(255,184,107,0.12)" },
  brain: { hex: "#B88CFF", bg: "rgba(184,140,255,0.12)" },
};

const ACT_COLORS: Record<string, { hex: string; bg: string; border: string }> = {
  save:    { hex: "#70E0A3", bg: "rgba(112,224,163,0.06)", border: "rgba(112,224,163,0.1)" },
  review:  { hex: "#FFB86B", bg: "rgba(255,184,107,0.06)", border: "rgba(255,184,107,0.1)" },
  brain:   { hex: "#B88CFF", bg: "rgba(184,140,255,0.06)", border: "rgba(184,140,255,0.1)" },
  synthesize: { hex: "#7C9CFF", bg: "rgba(124,156,255,0.06)", border: "rgba(124,156,255,0.1)" },
};

const COMMANDS = [
  { trigger: "/review", label: "Review Agent", desc: "审视你的想法", agentKey: "review" as const },
  { trigger: "/brain", label: "Brain Agent", desc: "联想扩展", agentKey: "brain" as const },
];

interface Action {
  id: string;
  label: string;
  shortcut: string;
}

const ACTIONS: Action[] = [
  { id: "save", label: "保存", shortcut: "Ctrl+S" },
  { id: "review", label: "挑战", shortcut: "Ctrl+R" },
  { id: "brain", label: "联想", shortcut: "Ctrl+B" },
  { id: "synthesize", label: "合成", shortcut: "" },
];

const showCommands = computed(() => input.value.startsWith("/") && !input.value.includes(" "));

const activeTag = computed(() => {
  const m = input.value.match(/#([a-zA-Z][a-zA-Z0-9_-]*)/);
  if (!m) return null;
  const tag = m[1].toLowerCase();
  const map: Record<string, string> = { review: "Review Agent", brain: "Brain Agent" };
  if (tag in map) return { tag, label: map[tag] };
  return null;
});

function handleAction(action: Action) {
  switch (action.id) {
    case "save":
      if (input.value.trim()) {
        input.value = "#save " + input.value;
        emit("send");
      }
      break;
    case "review":
      input.value = "#review " + input.value;
      emit("send");
      break;
    case "brain":
      input.value = "#brain " + input.value;
      emit("send");
      break;
    case "synthesize":
      input.value = "#synthesize " + input.value;
      emit("send");
      break;
  }
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
    <!-- / 命令面板 -->
    <div
      v-if="showCommands && input.length >= 1"
      class="absolute bottom-full left-4 right-4 mb-2 rounded-xl shadow-2xl overflow-hidden z-10 border"
      style="background: #20242D; border-color: #2C3240"
    >
      <div class="px-3 py-1.5 text-[10px] border-b" style="color: #9AA4B2; border-color: #2C3240">
        命令
      </div>
      <button
        v-for="cmd in COMMANDS"
        :key="cmd.trigger"
        class="w-full flex items-center gap-2.5 px-3 py-2 text-left transition-all"
        :class="input === cmd.trigger ? 'opacity-100' : 'opacity-60'"
        :style="{ background: input === cmd.trigger ? 'rgba(255,255,255,0.03)' : 'transparent' }"
        @click="emit('insertCommand', cmd.trigger)"
      >
        <span
          class="w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold shrink-0"
          :style="{ background: CMD_COLORS[cmd.agentKey].bg, color: CMD_COLORS[cmd.agentKey].hex }"
        >/</span>
        <div>
          <span class="text-xs" style="color: #F4F6FA">{{ cmd.trigger }}</span>
          <span class="text-[10px] ml-1.5" style="color: #9AA4B2">{{ cmd.desc }}</span>
        </div>
      </button>
    </div>

    <!-- Tag pill -->
    <div v-if="activeTag" class="mb-1.5 flex items-center gap-1.5 px-1">
      <span
        class="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full border"
        :style="{
          background: activeTag.tag === 'review' ? 'rgba(255,184,107,0.1)' : 'rgba(184,140,255,0.1)',
          borderColor: activeTag.tag === 'review' ? 'rgba(255,184,107,0.2)' : 'rgba(184,140,255,0.2)',
          color: activeTag.tag === 'review' ? '#FFB86B' : '#B88CFF',
        }"
      >
        <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        → {{ activeTag.label }}
      </span>
    </div>

    <!-- 输入区 -->
    <div
      class="flex items-end gap-2 rounded-2xl p-2 transition-colors border"
      style="background: #20242D; border-color: #2C3240"
    >
      <textarea
        :value="input"
        class="chat-input flex-1 bg-transparent text-sm resize-none outline-none leading-relaxed min-h-[40px] max-h-32 px-2 py-1.5"
        :placeholder="activeTag ? `#${activeTag.tag} 已激活…` : '输入碎片想法，#review / #brain 触发 Agent，/ 查看命令'"
        style="color: #F4F6FA"
        rows="1"
        @input="(e) => { input = (e.target as HTMLTextAreaElement).value; handleInput(e); }"
        @keydown="handleKeydown"
      />
      <button
        v-if="!streaming"
        :disabled="!input.trim()"
        class="w-8 h-8 rounded-xl flex items-center justify-center transition-all shrink-0"
        :style="{
          background: input.trim() ? '#7C9CFF' : 'rgba(255,255,255,0.05)',
          color: input.trim() ? '#fff' : '#9AA4B2',
          opacity: input.trim() ? 1 : 0.3,
        }"
        @click="emit('send')"
      >
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M12 5l7 7-7 7" />
        </svg>
      </button>
      <button
        v-else
        class="w-8 h-8 rounded-xl flex items-center justify-center transition-all shrink-0"
        style="background: rgba(255,107,107,0.2); color: #FF6B6B"
        @click="emit('abort')"
      >
        <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
          <rect x="6" y="6" width="12" height="12" rx="1" />
        </svg>
      </button>
    </div>

    <!-- 快捷动作栏 -->
    <div class="flex items-center gap-1.5 mt-2 px-1">
      <button
        v-for="action in ACTIONS"
        :key="action.id"
        class="flex items-center gap-1 text-[10px] px-2.5 py-1 rounded-full transition-all hover:brightness-110 border"
        :style="{
          background: ACT_COLORS[action.id].bg,
          borderColor: ACT_COLORS[action.id].border,
          color: ACT_COLORS[action.id].hex,
        }"
        @click="handleAction(action)"
      >
        {{ action.label }}
        <span
          v-if="action.shortcut"
          class="text-[8px] px-1 py-0.5 rounded font-mono"
          style="background: rgba(255,255,255,0.04); opacity: 0.6"
        >{{ action.shortcut }}</span>
      </button>

      <span class="flex-1" />

      <span class="text-[9px] opacity-30" style="color: #9AA4B2">
        Enter 发送 · Shift+Enter 换行
      </span>
    </div>
  </div>
</template>
