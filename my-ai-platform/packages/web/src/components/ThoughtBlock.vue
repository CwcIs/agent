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

const emit = defineEmits<{
  chipClick: [chip: InsightChipData];
}>();

const agentColor = computed(() => agentColors[props.agentId || ""] || null);
const agent = computed(() => (props.agentId ? agentMeta[props.agentId] : null));

function renderMarkdown(text: string): string {
  if (!text) return "";
  return DOMPurify.sanitize(marked.parse(text) as string);
}

function formatTime(ts: number): string {
  const date = new Date(ts);
  return `${date.getHours().toString().padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}`;
}
</script>

<template>
  <article class="thought-block" :class="role">
    <div class="block-label">
      <template v-if="role === 'user'">Your Thought</template>
      <template v-else>
        <span
          v-if="agentColor"
          class="agent-dot"
          :style="{ background: agentColor.hex, boxShadow: `0 0 16px ${agentColor.hex}66` }"
        />
        {{ agent?.label || agentId || 'AI Response' }}
      </template>
      <time>{{ formatTime(timestamp) }}</time>
    </div>

    <div v-if="role === 'user'" class="user-content">
      {{ content }}
    </div>

    <div v-else>
      <div
        v-if="content"
        class="prose prose-invert response-content"
        v-html="renderMarkdown(content)"
      />
      <div v-if="!done && !content" class="typing-line">
        <span :style="{ background: agentColor?.hex || 'var(--brand)' }" />
        正在组织回应…
      </div>
      <InsightChipBar
        v-if="insightChips && insightChips.length"
        :chips="insightChips"
        class="mt-4"
        @chip-click="emit('chipClick', $event)"
      />
    </div>
  </article>
</template>

<style scoped>
.thought-block {
  width: min(760px, calc(100% - 32px));
  margin: 0 auto 16px;
  border: 1px solid var(--border-subtle);
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(255,255,255,0.055), rgba(255,255,255,0.032));
  box-shadow: 0 18px 60px rgba(0,0,0,0.16), inset 0 1px 0 rgba(255,255,255,0.05);
  padding: 22px;
}

.thought-block.user {
  background: rgba(255,255,255,0.03);
}

.block-label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-tertiary);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-bottom: 13px;
}

.block-label time {
  margin-left: auto;
  font-size: 10px;
  letter-spacing: 0;
  text-transform: none;
  font-weight: 500;
}

.agent-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
}

.user-content,
.response-content {
  color: var(--text-primary);
  font-size: 15.5px;
  line-height: 1.78;
}

.response-content :deep(p) {
  margin: 0 0 0.9em;
}

.response-content :deep(p:last-child) {
  margin-bottom: 0;
}

.response-content :deep(ul),
.response-content :deep(ol) {
  margin: 0.75em 0;
  padding-left: 1.25em;
}

.typing-line {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 14px;
}

.typing-line span {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  animation: pulse-glow 1.4s ease-in-out infinite;
}
</style>
