<script setup lang="ts">
defineProps<{
  sidebarOpen: boolean;
  drawerOpen: boolean;
}>();
</script>

<template>
  <div class="app-frame">
    <div class="aurora aurora-one" />
    <div class="aurora aurora-two" />
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

.aurora {
  position: absolute;
  pointer-events: none;
  filter: blur(50px);
  opacity: 0.42;
}

.aurora-one {
  width: 360px;
  height: 360px;
  left: 260px;
  top: -190px;
  background: rgba(154, 134, 255, 0.22);
}

.aurora-two {
  width: 300px;
  height: 300px;
  right: 240px;
  bottom: -180px;
  background: rgba(121, 174, 255, 0.12);
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
