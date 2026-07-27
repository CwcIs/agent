<script setup lang="ts">
defineProps<{
  sidebarOpen: boolean;
  drawerOpen: boolean;
}>();
</script>

<template>
  <div class="app-frame">
    <slot name="left-rail" />
    <section class="studio-frame">
      <slot name="studio" />
    </section>
    <slot name="drawer" />
  </div>
</template>

<style scoped>
.app-frame {
  position: relative;
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background: transparent;
  color: var(--text-primary);
}

.studio-frame {
  position: relative;
  z-index: 1;
  flex: 1;
  min-width: 0;
  display: flex;
  overflow: hidden;
}
</style>
