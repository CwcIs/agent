<script setup lang="ts">
import { layout } from "../shared/design-tokens";

defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();
</script>

<template>
  <Transition name="drawer">
    <aside v-if="open" class="insight-drawer" :style="{ width: layout.drawerWidth }">
      <header class="drawer-head">
        <div>
          <span>Context</span>
          <strong><slot name="title">Insight</slot></strong>
        </div>
        <button title="关闭 (Esc)" @click="emit('close')">Esc</button>
      </header>
      <div class="drawer-body">
        <slot />
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.insight-drawer {
  position: relative;
  z-index: 3;
  flex-shrink: 0;
  border-left: 1px solid var(--border-subtle);
  background: rgba(10, 11, 16, 0.76);
  backdrop-filter: blur(28px);
  box-shadow: -24px 0 80px rgba(0,0,0,.28);
  overflow-y: auto;
}
.drawer-head {
  position: sticky;
  top: 0;
  z-index: 2;
  min-height: 72px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-subtle);
  background: rgba(10, 11, 16, 0.84);
  backdrop-filter: blur(24px);
}
.drawer-head div { display: grid; gap: 2px; }
.drawer-head span { color: var(--text-tertiary); font-size: 10px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }
.drawer-head strong { color: var(--text-primary); font-size: 15px; }
.drawer-head button { border: 1px solid var(--border-subtle); border-radius: 999px; background: rgba(255,255,255,.045); color: var(--text-tertiary); padding: 6px 9px; font-size: 11px; transition: 160ms ease; }
.drawer-head button:hover { color: var(--text-primary); border-color: var(--border-strong); }
.drawer-body { padding: 18px; }
</style>
