<script setup lang="ts">
/**
 * 根组件 — 三面板布局
 * 左侧：笔记列表 | 中间：Chat + Daily Digest | 右侧：暂无（Phase 2 Hub 面板）
 */
import ChatView from "./views/ChatView.vue";
import NoteListView from "./views/NoteListView.vue";
import DailyDigestPanel from "./views/DailyDigestPanel.vue";
</script>

<template>
  <div class="flex h-screen bg-gray-50">
    <!-- 左侧：笔记列表 -->
    <aside class="w-72 border-r bg-white p-4 overflow-y-auto">
      <NoteListView />
    </aside>

    <!-- 中间：主区域 -->
    <main class="flex-1 flex flex-col">
      <!-- 每日摘要面板 -->
      <DailyDigestPanel />
      <!-- Chat 界面 -->
      <ChatView />
    </main>
  </div>
</template>
