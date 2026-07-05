<script setup lang="ts">
import { computed } from "vue";
import { agentColors, radii } from "../shared/design-tokens";

const input = defineModel<string>("input", { default: "" });
const streaming = defineModel<boolean>("streaming", { default: false });

const emit = defineEmits<{
  send: [];
  abort: [];
  insertCommand: [cmd: string];
}>();

const COMMANDS = [
  { trigger: "/review", label: "Review", desc: "挑战隐含假设", agentKey: "review" as const },
  { trigger: "/brain", label: "Brain", desc: "联想扩展", agentKey: "brain" as const },
];

const showCommands = computed(() => input.value.startsWith("/") && !input.value.includes(" "));

const activeTag = computed(() => {
  const match = input.value.match(/#([a-zA-Z][a-zA-Z0-9_-]*)/);
  if (!match) return null;
  const tag = match[1].toLowerCase();
  const map: Record<string, string> = { review: "Review", brain: "Brain" };
  if (tag in map) return { tag, label: map[tag] };
  return null;
});

interface Suggestion {
  id: string;
  label: string;
  prefix: string;
  color: string;
}

const suggestions = computed<Suggestion[]>(() => {
  const text = input.value.trim();
  if (!text || text.startsWith("/") || text.startsWith("#")) return [];

  const items: Suggestion[] = [];
  if (text.length < 90) {
    items.push({ id: "save", label: "保存为笔记", prefix: "#save ", color: "var(--color-success)" });
  }
  if (/是否|应该|判断|假设|可能|不够|问题|风险|为什么/.test(text)) {
    items.push({ id: "review", label: "让 Review 挑战", prefix: "#review ", color: "var(--agent-review)" });
  }
  if (/想法|灵感|概念|联想|可能|如果|设想|方向/.test(text)) {
    items.push({ id: "brain", label: "让 Brain 发散", prefix: "#brain ", color: "var(--agent-brain)" });
  }
  return items.slice(0, 3);
});

function handleSuggestion(suggestion: Suggestion) {
  input.value = suggestion.prefix + input.value;
  emit("send");
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    emit("send");
  }
}

function handleInput(event: Event) {
  const el = event.target as HTMLTextAreaElement;
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}
</script>

<template>
  <div class="composer-zone">
    <div v-if="suggestions.length && !streaming" class="suggestion-row">
      <span>Suggested</span>
      <button
        v-for="suggestion in suggestions"
        :key="suggestion.id"
        :style="{ color: suggestion.color, borderColor: suggestion.color + '30', background: suggestion.color + '12' }"
        @click="handleSuggestion(suggestion)"
      >
        {{ suggestion.label }}
      </button>
    </div>

    <div v-if="showCommands && input.length >= 1" class="command-panel">
      <div class="command-title">Commands</div>
      <button
        v-for="cmd in COMMANDS"
        :key="cmd.trigger"
        class="command-item"
        @click="emit('insertCommand', cmd.trigger)"
      >
        <span :style="{ background: agentColors[cmd.agentKey].bg, color: agentColors[cmd.agentKey].hex }">/</span>
        <strong>{{ cmd.trigger }}</strong>
        <em>{{ cmd.desc }}</em>
      </button>
    </div>

    <div v-if="activeTag" class="active-tag">
      → {{ activeTag.label }} is active
    </div>

    <div class="composer-card" :style="{ borderRadius: radii.composer }">
      <textarea
        v-model="input"
        class="chat-input"
        :placeholder="activeTag ? `#${activeTag.tag} 已激活，继续写下你的想法…` : '写下一个想法、问题或碎片…'"
        rows="1"
        @keydown="handleKeydown"
        @input="handleInput"
      />

      <div class="composer-actions">
        <button @click="emit('insertCommand', '/review')">+ Review</button>
        <button @click="emit('insertCommand', '/brain')">+ Brain</button>
        <button># Tag</button>
        <div class="spacer" />
        <button v-if="!streaming" class="send-btn" :disabled="!input.trim()" @click="emit('send')">
          Send ↵
        </button>
        <button v-else class="stop-btn" @click="emit('abort')">Stop</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.composer-zone {
  position: relative;
  flex-shrink: 0;
  width: min(820px, calc(100% - 32px));
  margin: 0 auto;
  padding: 0 0 18px;
}

.suggestion-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 10px 10px;
}

.suggestion-row span {
  color: var(--text-tertiary);
  font-size: 11px;
}

.suggestion-row button,
.composer-actions button {
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: rgba(255,255,255,0.045);
  color: var(--text-secondary);
  padding: 7px 10px;
  font-size: 12px;
  transition: 150ms ease;
}

.suggestion-row button:hover,
.composer-actions button:hover {
  filter: brightness(1.12);
}

.command-panel {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 100%;
  z-index: 20;
  margin-bottom: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 18px;
  background: rgba(25,28,36,0.96);
  box-shadow: 0 24px 80px rgba(0,0,0,0.36);
  overflow: hidden;
}

.command-title {
  color: var(--text-tertiary);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 10px 14px 7px;
  border-bottom: 1px solid var(--border-subtle);
}

.command-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  text-align: left;
  transition: 150ms ease;
}

.command-item:hover {
  background: rgba(255,255,255,0.055);
}

.command-item span {
  width: 22px;
  height: 22px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-weight: 800;
}

.command-item strong {
  color: var(--text-primary);
  font-size: 13px;
}

.command-item em {
  color: var(--text-tertiary);
  font-style: normal;
  font-size: 12px;
}

.active-tag {
  width: fit-content;
  margin: 0 0 8px 10px;
  border: 1px solid var(--brand-border);
  border-radius: 999px;
  background: var(--brand-soft);
  color: var(--brand);
  padding: 5px 9px;
  font-size: 11px;
}

.composer-card {
  border: 1px solid rgba(255,255,255,0.13);
  background: rgba(25,28,36,0.94);
  box-shadow: 0 30px 90px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,255,255,0.08);
  overflow: hidden;
  backdrop-filter: blur(24px);
}

.chat-input {
  width: 100%;
  min-height: 66px;
  max-height: 170px;
  resize: none;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--text-primary);
  padding: 17px 19px 8px;
  font-size: 15px;
  line-height: 1.6;
}

.chat-input::placeholder {
  color: var(--text-tertiary);
}

.composer-actions {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 10px 10px;
}

.spacer { flex: 1; }

.send-btn {
  color: white !important;
  background: linear-gradient(135deg, var(--brand), #A792FF) !important;
  border-color: transparent !important;
  padding-inline: 14px !important;
}

.send-btn:disabled {
  opacity: 0.38;
  cursor: not-allowed;
}

.stop-btn {
  color: white !important;
  background: var(--color-danger) !important;
  border-color: transparent !important;
}
</style>
