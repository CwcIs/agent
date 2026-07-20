<script setup lang="ts">
import { computed } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { agentMeta, agentColors } from "../shared/design-tokens";
import InsightChipBar from "./InsightChipBar.vue";
import type { InsightChipData } from "./InsightChip.vue";

marked.setOptions({ breaks: true });

const props = defineProps<{
  role: "user" | "assistant";
  content: string;
  agentId?: string;
  done?: boolean;
  insightChips?: InsightChipData[];
  timestamp: number;
}>();

const emit = defineEmits<{ chipClick: [chip: InsightChipData] }>();

const agentColor = computed(() => agentColors[props.agentId || ""] || null);
const agent = computed(() => (props.agentId ? agentMeta[props.agentId] : null));

function renderMarkdown(text: string): string {
  return text ? DOMPurify.sanitize(marked.parse(text) as string) : "";
}

function formatTime(ts: number): string {
  const date = new Date(ts);
  return `${date.getHours().toString().padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}`;
}
</script>

<template>
  <article class="thought-block" :class="role">
    <header class="block-head">
      <div class="block-identity">
        <span v-if="role === 'assistant' && agentColor" class="agent-dot" :style="{ background: agentColor.hex, boxShadow: `0 0 16px ${agentColor.hex}66` }" />
        <span>{{ role === 'user' ? 'Your Thought' : agent?.label || agentId || 'AI Response' }}</span>
      </div>
      <time>{{ formatTime(timestamp) }}</time>
    </header>

    <div v-if="role === 'user'" class="content user-content">{{ content }}</div>
    <div v-else>
      <div v-if="content" class="prose prose-invert content response-content" v-html="renderMarkdown(content)" />
      <div v-if="!done && !content" class="typing-line">
        <span :style="{ background: agentColor?.hex || 'var(--brand)' }" />
        正在组织回应…
      </div>
      <InsightChipBar v-if="insightChips && insightChips.length" :chips="insightChips" class="chips" @chip-click="emit('chipClick', $event)" />
    </div>
  </article>
</template>

<style scoped>
.thought-block {
  width: min(760px, calc(100% - 32px));
  margin: 0 auto 16px;
  border: 1px solid var(--border-subtle);
  border-radius: 24px;
  padding: 22px;
  background: linear-gradient(180deg, rgba(255,255,255,.058), rgba(255,255,255,.032));
  box-shadow: 0 24px 80px rgba(0,0,0,.18), inset 0 1px 0 rgba(255,255,255,.06);
}
.thought-block.user { background: rgba(255,255,255,.028); box-shadow: inset 0 1px 0 rgba(255,255,255,.04); }
.block-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.block-identity { display: inline-flex; align-items: center; gap: 8px; color: var(--text-tertiary); font-size: 10px; font-weight: 850; letter-spacing: .13em; text-transform: uppercase; }
time { color: var(--text-tertiary); font-size: 11px; }
.agent-dot { width: 7px; height: 7px; border-radius: 999px; }
.content { color: var(--text-primary); font-size: 15.5px; line-height: 1.8; }
.response-content :deep(p) { margin: 0 0 .95em; }
.response-content :deep(p:last-child) { margin-bottom: 0; }
.response-content :deep(ul), .response-content :deep(ol) { margin: .9em 0; padding-left: 1.25em; }
.response-content :deep(blockquote) { border-left: 2px solid var(--brand-border); margin: 1em 0; padding-left: 1em; color: var(--text-secondary); }
.typing-line { display: inline-flex; align-items: center; gap: 9px; color: var(--text-secondary); font-size: 14px; }
.typing-line span { width: 7px; height: 7px; border-radius: 999px; animation: pulse-glow 1.4s ease-in-out infinite; }
.chips { margin-top: 16px; }
</style>
