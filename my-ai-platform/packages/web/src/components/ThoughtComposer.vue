<script setup lang="ts">
import { computed } from "vue";
import { agentColors } from "../shared/design-tokens";

const input = defineModel<string>("input", { default: "" });
const streaming = defineModel<boolean>("streaming", { default: false });

const emit = defineEmits<{
  send: [];
  abort: [];
  insertCommand: [cmd: string];
}>();

const COMMANDS = [
  { trigger: "/review", label: "Review", desc: "挑战假设", agentKey: "review" as const },
  { trigger: "/brain", label: "Brain", desc: "联想扩展", agentKey: "brain" as const },
];

const showCommands = computed(() => input.value.startsWith("/") && !input.value.includes(" "));
const activeTag = computed(() => {
  const match = input.value.match(/#([a-zA-Z][a-zA-Z0-9_-]*)/);
  if (!match) return null;
  const tag = match[1].toLowerCase();
  const map: Record<string, string> = { review: "Review", brain: "Brain", save: "Save" };
  return tag in map ? { tag, label: map[tag] } : null;
});

const suggestions = computed(() => {
  const text = input.value.trim();
  if (!text || text.startsWith("/") || text.startsWith("#")) return [];
  const items: Array<{ id: string; label: string; prefix: string; color: string }> = [];
  if (text.length < 90) items.push({ id: "save", label: "保存为笔记", prefix: "#save ", color: "var(--color-success)" });
  if (/是否|应该|判断|假设|可能|不够|问题|风险|为什么/.test(text)) items.push({ id: "review", label: "让 Review 挑战", prefix: "#review ", color: "var(--agent-review)" });
  if (/想法|灵感|概念|联想|可能|如果|设想|方向/.test(text)) items.push({ id: "brain", label: "让 Brain 发散", prefix: "#brain ", color: "var(--agent-brain)" });
  return items.slice(0, 3);
});

function handleSuggestion(suggestion: { prefix: string }) {
  input.value = suggestion.prefix + input.value;
  emit("send");
}

function insertMention(agentId: string) {
  const mention = `@${agentId} `;
  input.value = input.value.replace(/^@(knowledge|review|brain)\s+/, "");
  input.value = mention + input.value;
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
      <button v-for="suggestion in suggestions" :key="suggestion.id" :style="{ color: suggestion.color, borderColor: suggestion.color + '30', background: suggestion.color + '12' }" @click="handleSuggestion(suggestion)">
        {{ suggestion.label }}
      </button>
    </div>

    <div v-if="showCommands && input.length >= 1" class="command-panel">
      <div class="command-title">Commands</div>
      <button v-for="cmd in COMMANDS" :key="cmd.trigger" class="command-item" @click="emit('insertCommand', cmd.trigger)">
        <span :style="{ background: agentColors[cmd.agentKey].bg, color: agentColors[cmd.agentKey].hex }">/</span>
        <strong>{{ cmd.trigger }}</strong>
        <em>{{ cmd.desc }}</em>
      </button>
    </div>

    <div class="composer-card" :class="{ active: activeTag }">
      <div v-if="activeTag" class="active-tag">{{ activeTag.label }} active</div>
      <textarea
        v-model="input"
        class="chat-input"
        :placeholder="activeTag ? `#${activeTag.tag} 已激活，继续写下你的想法…` : '写下一个想法、问题或碎片…'"
        rows="1"
        @keydown="handleKeydown"
        @input="handleInput"
      />
      <footer class="composer-actions">
        <span class="route-label">Route to</span>
        <button class="agent-route knowledge" title="交给 Knowledge Agent" @click="insertMention('knowledge')">@K</button>
        <button class="agent-route review" title="交给 Review Agent" @click="insertMention('review')">@R</button>
        <button class="agent-route brain" title="交给 Brain Agent" @click="insertMention('brain')">@B</button>
        <div class="spacer" />
        <button v-if="!streaming" class="send-btn" :disabled="!input.trim()" title="发送" aria-label="发送" @click="emit('send')">↑</button>
        <button v-else class="stop-btn" title="停止生成" aria-label="停止生成" @click="emit('abort')">■</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.composer-zone { position: relative; flex-shrink: 0; width: min(820px, calc(100% - 32px)); margin: 0 auto; padding: 0 0 22px; }
.suggestion-row { display: flex; align-items: center; gap: 8px; margin: 0 12px 10px; }
.suggestion-row span { color: var(--text-tertiary); font-size: 11px; }
.suggestion-row button, .composer-actions button { border: 1px solid var(--border-subtle); border-radius: 6px; background: rgba(255,255,255,.04); color: var(--text-secondary); padding: 7px 9px; font-size: 11px; transition: 160ms ease; }
.suggestion-row button:hover, .composer-actions button:hover { transform: translateY(-1px); filter: brightness(1.12); }
.command-panel { position: absolute; left: 0; right: 0; bottom: 100%; z-index: 20; margin-bottom: 12px; border: 1px solid var(--border-subtle); border-radius: 8px; background: rgba(19,21,31,.96); box-shadow: 0 24px 80px rgba(0,0,0,.38); overflow: hidden; }
.command-title { color: var(--text-tertiary); font-size: 10px; letter-spacing: .12em; text-transform: uppercase; padding: 11px 15px 8px; border-bottom: 1px solid var(--border-subtle); }
.command-item { width: 100%; display: flex; align-items: center; gap: 10px; padding: 12px 15px; text-align: left; transition: 160ms ease; }
.command-item:hover { background: rgba(255,255,255,.055); }
.command-item span { width: 24px; height: 24px; border-radius: 9px; display: grid; place-items: center; font-weight: 850; }
.command-item strong { color: var(--text-primary); font-size: 13px; }
.command-item em { color: var(--text-tertiary); font-style: normal; font-size: 12px; }
.composer-card { position: relative; border: 1px solid rgba(255,255,255,.14); border-radius: 8px; background: #141a20; box-shadow: 0 18px 60px rgba(0,0,0,.34), inset 0 1px 0 rgba(255,255,255,.05); overflow: hidden; }
.composer-card.active { border-color: var(--brand-border); box-shadow: 0 32px 100px rgba(0,0,0,.42), 0 0 0 1px var(--brand-border), inset 0 1px 0 rgba(255,255,255,.08); }
.active-tag { position: absolute; top: 10px; right: 12px; border: 1px solid var(--brand-border); border-radius: 5px; background: var(--brand-soft); color: var(--brand-2); padding: 4px 8px; font-size: 10px; }
.chat-input { width: 100%; min-height: 74px; max-height: 180px; resize: none; border: 0; outline: none; background: transparent; color: var(--text-primary); padding: 19px 20px 8px; font-size: 15px; line-height: 1.65; }
.chat-input::placeholder { color: var(--text-tertiary); }
.composer-actions { display: flex; align-items: center; gap: 8px; padding: 8px 11px 11px; }
.route-label { color: var(--text-tertiary); font-size: 10px; }
.agent-route.knowledge { color: var(--agent-knowledge); }
.agent-route.review { color: var(--agent-review); }
.agent-route.brain { color: var(--agent-brain); }
.spacer { flex: 1; }
.send-btn, .stop-btn { width: 32px; height: 32px; padding: 0 !important; display: grid; place-items: center; font-size: 16px !important; }
.send-btn { color: #0b1316 !important; background: #a8dce6 !important; border-color: transparent !important; }
.send-btn:disabled { opacity: .38; transform: none !important; }
.stop-btn { color: white !important; background: var(--color-danger) !important; border-color: transparent !important; }
</style>
