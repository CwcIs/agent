<script setup lang="ts">
import { computed } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";
import ToolCallCard from "./ToolCallCard.vue";

marked.setOptions({ breaks: true });

function renderMarkdown(text: string): string {
  const raw = marked.parse(text) as string;
  return DOMPurify.sanitize(raw);
}

interface ToolCall {
  name: string;
  input?: Record<string, unknown>;
  result?: string;
  status: "running" | "done";
  expanded?: boolean;
  isError?: boolean;
}

const props = defineProps<{
  role: "user" | "assistant";
  content: string;
  agentId?: string;
  done?: boolean;
  toolCalls?: ToolCall[];
  timestamp: number;
}>();

const AGENT_LABEL: Record<string, string> = {
  knowledge: "Knowledge",
  review: "Review",
  brain: "Brain",
};

const AGENT_ICON: Record<string, string> = {
  knowledge: "K",
  review: "R",
  brain: "B",
};

// Direct color values for JS inline styles
const AGENT_HEX: Record<string, string> = {
  knowledge: "#7C9CFF",
  review: "#FFB86B",
  brain: "#B88CFF",
};

const AGENT_BG: Record<string, string> = {
  knowledge: "rgba(124,156,255,0.12)",
  review: "rgba(255,184,107,0.12)",
  brain: "rgba(184,140,255,0.12)",
};

const agentColor = computed(() => AGENT_HEX[props.agentId || "knowledge"] || "#9AA4B2");
const agentBg = computed(() => AGENT_BG[props.agentId || "knowledge"] || "rgba(255,255,255,0.08)");
const agentIcon = computed(() => AGENT_ICON[props.agentId || "knowledge"] || "?");
const agentLabel = computed(() => AGENT_LABEL[props.agentId || ""] || props.agentId || "");

function formatTime(ts: number): string {
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}
</script>

<template>
  <div
    :class="['flex gap-2.5 group', role === 'user' ? 'flex-row-reverse' : 'flex-row']"
  >
    <!-- 头像 -->
    <div
      v-if="role === 'assistant'"
      class="w-7 h-7 rounded-lg shrink-0 flex items-center justify-center text-[10px] font-semibold mt-0.5"
      :style="{ background: agentBg, color: agentColor }"
    >
      {{ agentIcon }}
    </div>

    <!-- 气泡 -->
    <div
      :class="[
        'rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed relative',
        role === 'user'
          ? 'rounded-tr-sm max-w-[72%]'
          : 'max-w-[80%] rounded-tl-sm',
      ]"
      :style="{
        background: role === 'user'
          ? 'rgba(124,156,255,0.25)'
          : 'rgba(255,255,255,0.03)',
        border: role === 'user'
          ? 'none'
          : '1px solid rgba(255,255,255,0.05)',
        color: role === 'user' ? '#fff' : '#F4F6FA',
      }"
    >
      <!-- Agent 名 -->
      <div v-if="agentId && agentLabel" class="flex items-center gap-2 mb-1">
        <span class="text-[10px] font-medium" :style="{ color: agentColor }">
          {{ agentLabel }}
        </span>
      </div>

      <!-- 内容 -->
      <div v-if="role === 'assistant'" class="prose prose-invert prose-sm max-w-none">
        <span v-html="renderMarkdown(content)" />
        <span
          v-if="!done"
          class="inline-block w-0.5 h-3.5 ml-0.5 animate-pulse align-text-bottom"
          :style="{ background: agentColor }"
        />
      </div>
      <div v-else class="whitespace-pre-wrap">{{ content }}</div>

      <!-- 时间戳 -->
      <div
        class="absolute -bottom-5 text-[9px] opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
        :class="role === 'user' ? 'right-0' : 'left-0'"
        style="color: #9AA4B2"
      >{{ formatTime(timestamp) }}</div>

      <!-- 工具调用卡片 -->
      <div v-if="toolCalls?.length" class="mt-2.5 space-y-1.5">
        <ToolCallCard
          v-for="(tc, ti) in toolCalls"
          :key="ti"
          :name="tc.name"
          :input="tc.input"
          :result="tc.result"
          :status="tc.status"
          :is-error="tc.isError"
          v-model:expanded="tc.expanded"
        />
      </div>
    </div>

    <!-- 用户头像 -->
    <div
      v-if="role === 'user'"
      class="w-7 h-7 rounded-lg shrink-0 flex items-center justify-center text-[10px] font-semibold mt-0.5"
      style="background: rgba(124,156,255,0.12); color: #7C9CFF"
    >U</div>
  </div>
</template>
