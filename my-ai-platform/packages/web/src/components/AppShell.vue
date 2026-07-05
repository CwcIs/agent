<script setup lang="ts">
defineProps<{
  sidebarOpen: boolean;
  drawerOpen: boolean;
}>();
</script>

<template>
  <div
    class="flex h-screen overflow-hidden"
    style="font-family: -apple-system, 'SF Pro Text', system-ui, sans-serif; background: var(--app-bg); color: var(--text-primary)"
  >
    <!-- Left Rail -->
    <slot name="left-rail" />

    <!-- Main Studio -->
    <slot name="studio" />

    <!-- Right Insight Drawer -->
    <slot name="drawer" />
  </div>
</template>
