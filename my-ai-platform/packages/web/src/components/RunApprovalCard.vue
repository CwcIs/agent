<script setup lang="ts">
defineProps<{
  targetAgent: string;
  risk: string;
  reason: string;
  resolving?: boolean;
}>();

const emit = defineEmits<{
  resolve: [approved: boolean];
}>();
</script>

<template>
  <section class="approval-card" aria-live="polite">
    <div>
      <span class="risk">{{ risk || "需要确认" }}</span>
      <strong>是否允许交给 {{ targetAgent }}？</strong>
      <p>{{ reason || "该协作请求需要你的明确确认。" }}</p>
    </div>
    <div class="actions">
      <button :disabled="resolving" class="reject" @click="emit('resolve', false)">拒绝</button>
      <button :disabled="resolving" class="approve" @click="emit('resolve', true)">
        {{ resolving ? "处理中…" : "允许并继续" }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.approval-card { width:min(760px,calc(100% - 32px));margin:10px auto 0;display:flex;align-items:center;justify-content:space-between;gap:20px;border:1px solid rgba(245,185,66,.28);border-radius:14px;padding:14px 16px;background:rgba(245,185,66,.07);color:var(--text-secondary) }
.approval-card strong { display:block;margin-top:6px;color:var(--text-primary);font-size:13px }
.approval-card p { margin-top:4px;font-size:11px;color:var(--text-tertiary) }
.risk { border-radius:999px;padding:3px 7px;background:rgba(245,185,66,.12);color:#f5c15d;font-size:9px;font-weight:700 }
.actions { display:flex;gap:7px;flex-shrink:0 }.actions button{border-radius:8px;padding:7px 10px;font-size:11px}.reject{color:var(--text-secondary);background:rgba(255,255,255,.05)}.approve{color:#10131a;background:#f5c15d}.actions button:disabled{opacity:.55}
</style>
