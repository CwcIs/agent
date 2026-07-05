<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  agentId: string;
  label: string;
  verb?: string;
  verdict?: string | null;
  verdictWarning?: string | null;
}>();

// Direct color values for JS inline styles
const AGENT_HEX: Record<string, string> = {
  knowledge: "#7C9CFF",
  review: "#FFB86B",
  brain: "#B88CFF",
};

const AGENT_BG: Record<string, string> = {
  knowledge: "rgba(124,156,255,0.08)",
  review: "rgba(255,184,107,0.08)",
  brain: "rgba(184,140,255,0.08)",
};

const AGENT_ROLE: Record<string, string> = {
  knowledge: "正在整理相关记忆",
  review: "正在挑战你的假设",
  brain: "正在做联想扩展",
};

const AGENT_ICON: Record<string, string> = {
  knowledge: "K",
  review: "R",
  brain: "B",
};

const agentColor = computed(() => AGENT_HEX[props.agentId] || "#9AA4B2");
const agentBg = computed(() => AGENT_BG[props.agentId] || "rgba(255,255,255,0.06)");
const agentRole = computed(() => AGENT_ROLE[props.agentId] || "正在处理");
const agentIcon = computed(() => AGENT_ICON[props.agentId] || "?");

const verdictLabel = computed(() => {
  if (!props.verdict) return null;
  switch (props.verdict) {
    case "natural_end": return "自然结束";
    case "missing_handoff": return "可能需要接力但未指定";
    case "loop_detected": return "检测到循环";
    case "max_depth_reached": return "已达最大深度";
    default: return props.verdict;
  }
});
</script>

<template>
  <div class="flex flex-col items-center gap-1.5 py-2 max-w-[80%] mx-auto">
    <!-- 分隔线 + Agent 标签 -->
    <div class="flex items-center gap-2.5 w-full">
      <div class="flex-1 h-px" style="background: linear-gradient(to right, transparent, #2C3240)" />
      <div
        class="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-medium shrink-0"
        :style="{
          background: agentBg,
          border: `1px solid ${agentColor}22`,
          color: agentColor,
        }"
      >
        <span
          class="w-4 h-4 rounded flex items-center justify-center text-[8px] font-bold shrink-0"
          :style="{ background: agentColor + '22', color: agentColor }"
        >{{ agentIcon }}</span>
        <span>{{ label }}</span>
        <span class="opacity-60">·</span>
        <span class="opacity-60 font-normal">{{ verb || agentRole }}</span>
      </div>
      <div class="flex-1 h-px" style="background: linear-gradient(to left, transparent, #2C3240)" />
    </div>

    <!-- Verdict 提示 -->
    <div
      v-if="verdict"
      class="text-[9px] px-2 py-0.5 rounded-full"
      :style="{
        background: verdict === 'loop_detected' || verdict === 'max_depth_reached'
          ? 'rgba(255,107,107,0.08)'
          : verdict === 'missing_handoff'
            ? 'rgba(255,209,102,0.08)'
            : 'rgba(112,224,163,0.06)',
        color: verdict === 'loop_detected' || verdict === 'max_depth_reached'
          ? '#FF6B6B'
          : verdict === 'missing_handoff'
            ? '#FFD166'
            : '#70E0A3',
      }"
    >
      <template v-if="verdict === 'loop_detected'">
        ⚠ 这条 Handoff Chain 似乎绕回来了，已停止继续调度
      </template>
      <template v-else-if="verdict === 'missing_handoff'">
        ⚡ {{ verdictWarning || '模型提到了需要别人，但没有明确 @agent' }}
      </template>
      <template v-else-if="verdict === 'max_depth_reached'">
        ⚠ 已达到最大调度深度，链自动终止
      </template>
      <template v-else>
        ✓ {{ verdictLabel }}
      </template>
    </div>
  </div>
</template>
