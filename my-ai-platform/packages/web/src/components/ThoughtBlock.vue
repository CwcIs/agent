<script setup lang="ts">
/**
 * ThoughtBlock — 文档块风格消息渲染（替代聊天气泡 MessageBlock）。
 *
 * 设计要点：
 * - 用户消息：左对齐，细线顶部分隔，简洁的"想法块"
 * - AI 回复：左对齐，agent 指示点 + markdown 正文 + InsightChips + 流式光标
 * - 不与聊天气泡混用：不区分左右对齐
 */
import { computed } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { agentMeta, agentColors, colors } from "../shared/design-tokens";
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
const agentMeta_ = computed(() => (props.agentId ? agentMeta[props.agentId] : null));

function renderMarkdown(text: string): string {
  if (!text) return "";
  return DOMPurify.sanitize(marked.parse(text) as string);
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}
</script>

<template>
  <div class="max-w-content mx-auto w-full">
    <!-- User Thought -->
    <div v-if="role === 'user'" class="py-4">
      <div class="text-[15px] leading-relaxed" :style="{ color: 'var(--text-primary)' }">
        {{ content }}
      </div>
      <div class="flex items-center gap-2 mt-1.5 text-[10px]" :style="{ color: 'var(--text-tertiary)' }">
        {{ formatTime(timestamp) }}
      </div>
    </div>

    <!-- AI Response -->
    <div v-else class="py-4 border-t" :style="{ borderColor: 'var(--border-subtle)' }">
      <!-- Agent indicator -->
      <div class="flex items-center gap-2 mb-3">
        <span
          v-if="agentMeta_"
          class="w-2 h-2 rounded-full shrink-0"
          :style="{ background: `var(--agent-${agentId})` }"
        />
        <span class="text-[11px] font-medium" :style="{ color: 'var(--text-secondary)' }">
          {{ agentMeta_?.label || agentId || 'AI' }}
        </span>
        <span class="text-[10px] ml-auto" :style="{ color: 'var(--text-tertiary)' }">
          {{ formatTime(timestamp) }}
        </span>
      </div>

      <!-- Content -->
      <div
        v-if="content"
        class="prose prose-invert text-[15px] leading-relaxed"
        :style="{ color: 'var(--text-primary)' }"
        v-html="renderMarkdown(content)"
      />

      <!-- Streaming cursor -->
      <span
        v-if="!done && !content"
        class="inline-block w-0.5 h-5 align-text-bottom animate-pulse-glow rounded-full"
        :style="{ background: `var(--agent-${agentId || 'knowledge'})` }"
      />

      <!-- Insight Chips -->
      <InsightChipBar
        v-if="insightChips && insightChips.length"
        :chips="insightChips"
        class="mt-3"
        @chip-click="emit('chipClick', $event)"
      />
    </div>
  </div>
</template>
