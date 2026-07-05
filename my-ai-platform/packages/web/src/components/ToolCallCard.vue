<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  name: string;
  input?: Record<string, unknown>;
  result?: string;
  status: "running" | "done";
  isError?: boolean;
}>();

const emit = defineEmits<{
  toggleExpand: [];
}>();

const expanded = defineModel<boolean>("expanded", { default: false });

// ── 自然语言摘要 ──
const summary = computed(() => {
  const input = props.input ?? {};
  switch (props.name) {
    case "search_notes": {
      const k = (input as any)?.k ?? (input as any)?.limit ?? "?";
      const q = (input as any)?.query ?? "";
      const snippet = typeof q === "string" ? (q.length > 30 ? q.slice(0, 30) + "…" : q) : "";
      return snippet ? `检索「${snippet}」相关笔记 (top ${k})` : `检索了 ${k} 条相关笔记`;
    }
    case "get_note": {
      const nid = (input as any)?.note_id ?? (input as any)?.id ?? "?";
      return `读取笔记 ${typeof nid === "string" ? nid.slice(0, 8) : nid}`;
    }
    case "save_note": {
      const t = (input as any)?.title ?? "";
      return t ? `保存笔记「${t}」` : "保存为新笔记";
    }
    case "get_notes_summary":
      return "获取笔记库摘要";
    case "synthesize_notes": {
      const ids = (input as any)?.note_ids ?? [];
      return `合成 ${Array.isArray(ids) ? ids.length : '?'} 条相关笔记`;
    }
    case "archive_note": {
      const nid = (input as any)?.note_id ?? "?";
      return `归档笔记 ${typeof nid === "string" ? nid.slice(0, 8) : nid}`;
    }
    default:
      return props.name.replace(/_/g, " ");
  }
});

// ── 关联笔记提取 ──
const relatedNoteIds = computed(() => {
  if (!props.result) return [];
  try {
    const r = JSON.parse(props.result);
    const ids: string[] = [];
    if (Array.isArray(r)) {
      for (const item of r) {
        if (item?.id) ids.push(item.id);
        if (item?.note_id) ids.push(item.note_id);
      }
    }
    if (r?.notes && Array.isArray(r.notes)) {
      for (const n of r.notes) {
        if (n?.id) ids.push(n.id);
      }
    }
    return [...new Set(ids)].slice(0, 5);
  } catch {
    return [];
  }
});
</script>

<template>
  <div
    class="rounded-lg border overflow-hidden transition-colors text-[11px]"
    :style="{
      borderColor: isError
        ? 'rgba(255,107,107,0.15)'
        : status === 'running'
          ? 'rgba(124,156,255,0.15)'
          : 'rgba(112,224,163,0.08)',
      background: isError
        ? 'rgba(255,107,107,0.03)'
        : status === 'running'
          ? 'rgba(124,156,255,0.03)'
          : 'rgba(112,224,163,0.02)',
    }"
  >
    <!-- 摘要行 -->
    <div
      class="flex items-center gap-2 px-2.5 py-2 cursor-pointer select-none hover:brightness-110 transition-all"
      @click="expanded = !expanded"
    >
      <!-- 状态图标 -->
      <svg
        v-if="status === 'running'"
        class="w-3 h-3 animate-spin shrink-0"
        style="color: var(--agent-knowledge)"
        fill="none" viewBox="0 0 24 24"
      >
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      <svg
        v-else-if="isError"
        class="w-3 h-3 shrink-0"
        style="color: var(--color-danger)"
        fill="none" stroke="currentColor" viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
      </svg>
      <svg
        v-else
        class="w-3 h-3 shrink-0"
        style="color: var(--color-success)"
        fill="none" stroke="currentColor" viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
      </svg>

      <span style="color: var(--text-muted)">{{ summary }}</span>

      <span v-if="status === 'running'" class="text-[9px] animate-pulse" style="color: var(--agent-knowledge)">执行中</span>
      <span v-else-if="isError" class="text-[9px]" style="color: var(--color-danger)">失败</span>
      <span v-else class="text-[9px]" style="color: var(--color-success)">完成</span>

      <!-- 关联笔记标签 -->
      <span
        v-for="nid in relatedNoteIds"
        :key="nid"
        class="text-[9px] px-1 py-0.5 rounded font-mono shrink-0"
        style="background: rgba(255,255,255,0.04); color: var(--text-muted)"
      >{{ nid.slice(0, 6) }}</span>

      <svg
        class="w-2.5 h-2.5 ml-auto transition-transform shrink-0"
        :class="{ 'rotate-180': expanded }"
        style="color: var(--text-muted); opacity: 0.5"
        fill="none" stroke="currentColor" viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
      </svg>
    </div>

    <!-- 展开详情 -->
    <div
      v-if="expanded"
      class="px-2.5 pb-2.5 space-y-2 border-t"
      style="border-color: rgba(255,255,255,0.04)"
    >
      <div v-if="input && Object.keys(input).length" class="text-[10px]">
        <span class="font-medium" style="color: var(--text-muted)">输入参数</span>
        <pre
          class="mt-1 rounded-lg p-2 overflow-x-auto max-h-24"
          style="background: rgba(0,0,0,0.2); color: var(--text-muted); opacity: 0.7"
        >{{ JSON.stringify(input, null, 2) }}</pre>
      </div>
      <div v-if="result" class="text-[10px]">
        <span class="font-medium" style="color: var(--text-muted)">返回结果</span>
        <pre
          class="mt-1 rounded-lg p-2 overflow-x-auto max-h-32"
          :style="{
            background: 'rgba(0,0,0,0.2)',
            color: isError ? 'var(--color-danger)' : 'var(--text-muted)',
            opacity: 0.7,
          }"
        >{{ result.length > 2000 ? result.slice(0, 2000) + '\n…(已截断)' : result }}</pre>
      </div>
    </div>
  </div>
</template>
