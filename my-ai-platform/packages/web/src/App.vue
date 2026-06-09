<script setup lang="ts">
import { ref } from "vue";
import ChatView from "./views/ChatView.vue";
import NoteListView from "./views/NoteListView.vue";
import DailyDigestPanel from "./views/DailyDigestPanel.vue";

const sidebarOpen = ref(true);
</script>

<template>
  <div class="flex h-screen bg-[#0d0d0d] text-gray-100 overflow-hidden" style="font-family: -apple-system, 'SF Pro Text', system-ui, sans-serif;">
    <!-- 左侧笔记栏 -->
    <transition name="sidebar">
      <aside
        v-show="sidebarOpen"
        class="flex flex-col w-60 shrink-0 border-r border-white/[0.06] bg-[#111111]"
      >
        <div class="flex items-center justify-between px-4 h-12 border-b border-white/[0.06]">
          <span class="text-[11px] font-semibold text-gray-500 tracking-[0.12em] uppercase">笔记库</span>
          <button @click="sidebarOpen = false" class="p-1 rounded hover:bg-white/5 text-gray-600 hover:text-gray-400 transition-colors">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 19l-7-7 7-7" />
            </svg>
          </button>
        </div>
        <div class="flex-1 overflow-y-auto">
          <NoteListView />
        </div>
      </aside>
    </transition>

    <!-- 主区域 -->
    <main class="flex-1 flex flex-col min-w-0">
      <!-- 顶栏 -->
      <header class="flex items-center gap-3 px-5 h-12 border-b border-white/[0.06] shrink-0">
        <button
          v-if="!sidebarOpen"
          @click="sidebarOpen = true"
          class="p-1 rounded hover:bg-white/5 text-gray-600 hover:text-gray-400 transition-colors"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <span class="text-sm font-medium text-gray-300">知识工作台</span>
        <div class="ml-auto flex items-center gap-2">
          <span class="text-[11px] text-gray-600 px-2 py-0.5 rounded-full border border-white/[0.06]">Phase 1</span>
        </div>
      </header>

      <!-- 每日回顾 -->
      <DailyDigestPanel />

      <!-- Chat -->
      <ChatView />
    </main>
  </div>
</template>

<style>
* { box-sizing: border-box; }
body { margin: 0; background: #0d0d0d; }

.sidebar-enter-active,
.sidebar-leave-active {
  transition: width 0.2s ease, opacity 0.2s ease;
  overflow: hidden;
}
.sidebar-enter-from,
.sidebar-leave-to {
  width: 0;
  opacity: 0;
}
.sidebar-enter-to,
.sidebar-leave-from {
  width: 240px;
  opacity: 1;
}

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.18); }
</style>
