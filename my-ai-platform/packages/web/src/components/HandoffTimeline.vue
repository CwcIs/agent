<script setup lang="ts">
import { computed } from "vue";

interface HandoffStep {
  from: string;
  to: string;
  trigger: string;
}

const props = defineProps<{
  steps: HandoffStep[];
  verdict?: string | null;
  verdictReason?: string | null;
}>();

const AGENT_LABEL: Record<string, string> = {
  knowledge: "Knowledge",
  review: "Review",
  brain: "Brain",
};

const AGENT_HEX: Record<string, string> = {
  knowledge: "#7C9CFF",
  review: "#FFB86B",
  brain: "#B88CFF",
};

const AGENT_BG: Record<string, string> = {
  knowledge: "rgba(124,156,255,0.1)",
  review: "rgba(255,184,107,0.1)",
  brain: "rgba(184,140,255,0.1)",
};

const hasContent = computed(() => props.steps.length > 0 || props.verdict);

function verdictStyle(v: string) {
  if (v === "natural_end") return { bg: "rgba(112,224,163,0.06)", color: "#70E0A3" };
  if (v === "loop_detected" || v === "max_depth_reached") return { bg: "rgba(255,107,107,0.08)", color: "#FF6B6B" };
  return { bg: "rgba(255,209,102,0.08)", color: "#FFD166" };
}
</script>

<template>
  <div
    v-if="hasContent"
    class="rounded-xl px-4 py-3 border"
    style="background: rgba(255,255,255,0.02); border-color: #2C3240"
  >
    <span class="text-[10px] font-medium uppercase tracking-wide" style="color: #9AA4B2">
      Handoff Chain
    </span>

    <!-- 步骤列表 -->
    <div v-if="steps.length" class="mt-2 flex items-center gap-1.5 flex-wrap">
      <template v-for="(step, i) in steps" :key="i">
        <span
          class="text-[10px] px-1.5 py-0.5 rounded font-medium"
          :style="{ background: AGENT_BG[step.from] || 'rgba(255,255,255,0.06)', color: AGENT_HEX[step.from] || '#9AA4B2' }"
        >
          {{ AGENT_LABEL[step.from] || step.from }}
        </span>
        <svg class="w-3 h-3" style="color: #9AA4B2; opacity: 0.4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </template>
      <span
        v-if="steps.length"
        class="text-[10px] px-1.5 py-0.5 rounded font-medium"
        :style="{
          background: AGENT_BG[steps[steps.length - 1].to] || 'rgba(255,255,255,0.06)',
          color: AGENT_HEX[steps[steps.length - 1].to] || '#9AA4B2',
        }"
      >
        {{ AGENT_LABEL[steps[steps.length - 1].to] || steps[steps.length - 1].to }}
      </span>
    </div>

    <!-- 详细触发说明 -->
    <div v-if="steps.length" class="mt-2 space-y-1">
      <div
        v-for="(step, i) in steps"
        :key="i"
        class="text-[10px]"
        style="color: #9AA4B2; opacity: 0.6"
      >
        <span :style="{ color: AGENT_HEX[step.from] || '#9AA4B2' }">
          {{ AGENT_LABEL[step.from] || step.from }}
        </span>
        触发
        <span :style="{ color: AGENT_HEX[step.to] || '#9AA4B2' }">
          @{{ step.to }}
        </span>
        <template v-if="step.trigger"> — "{{ step.trigger.slice(0, 60) }}{{ step.trigger.length > 60 ? '…' : '' }}"</template>
      </div>
    </div>

    <!-- Verdict -->
    <div
      v-if="verdict"
      class="mt-2 text-[10px] px-2 py-1 rounded"
      :style="{ background: verdictStyle(verdict).bg, color: verdictStyle(verdict).color }"
    >
      {{ verdictReason || verdict }}
    </div>
  </div>
</template>
