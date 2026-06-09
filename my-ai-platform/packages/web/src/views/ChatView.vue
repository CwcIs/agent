<script setup lang="ts">
import { ref, nextTick, onUnmounted, computed } from "vue";
import { marked } from "marked";

marked.setOptions({ breaks: true });

interface Message {
  role: "user" | "assistant";
  content: string;
  agentId?: string;
  done?: boolean;
}

const messages = ref<Message[]>([]);
const input = ref("");
const streaming = ref(false);
const messagesEl = ref<HTMLElement | null>(null);
let eventSource: EventSource | null = null;

async function scrollBottom() {
  await nextTick();
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
  }
}

function sendMessage() {
  if (!input.value.trim() || streaming.value) return;

  messages.value.push({ role: "user", content: input.value, done: true });
  streaming.value = true;
  scrollBottom();

  const encoded = encodeURIComponent(input.value);
  eventSource = new EventSource(`/chat/stream?input=${encoded}`);

  eventSource.addEventListener("token", (e) => {
    const last = messages.value[messages.value.length - 1];
    if (last?.role === "assistant" && !last.done) {
      last.content += e.data;
    } else {
      messages.value.push({ role: "assistant", content: e.data, done: false });
    }
    scrollBottom();
  });

  eventSource.addEventListener("text", (e) => {
    const data = JSON.parse(e.data);
    const last = messages.value[messages.value.length - 1];
    if (last?.role === "assistant" && !last.done) {
      last.content += data.delta;
    } else {
      messages.value.push({ role: "assistant", content: data.delta, agentId: data.agentId, done: false });
    }
    scrollBottom();
  });

  eventSource.addEventListener("done", () => {
    const last = messages.value[messages.value.length - 1];
    if (last) last.done = true;
    streaming.value = false;
    eventSource?.close();
  });

  eventSource.onerror = () => {
    const last = messages.value[messages.value.length - 1];
    if (last) last.done = true;
    streaming.value = false;
    eventSource?.close();
  };

  input.value = "";
}

function abortStream() {
  eventSource?.close();
  streaming.value = false;
  const last = messages.value[messages.value.length - 1];
  if (last) last.done = true;
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

onUnmounted(() => {
  eventSource?.close();
});
</script>

<template>
  <div class="flex-1 flex flex-col min-h-0">
    <!-- 消息列表 -->
    <div ref="messagesEl" class="flex-1 overflow-y-auto px-5 py-4 space-y-5">
      <!-- 空状态 -->
      <div v-if="!messages.length" class="flex flex-col items-center justify-center h-full gap-3 text-center">
        <div class="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center">
          <svg class="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
        <p class="text-sm text-gray-500">输入碎片想法，AI 帮你整理成结构化笔记</p>
        <p class="text-xs text-gray-700">⏎ 发送 · Shift+⏎ 换行</p>
      </div>

      <!-- 消息气泡 -->
      <div
        v-for="(msg, i) in messages"
        :key="i"
        :class="['flex gap-3', msg.role === 'user' ? 'flex-row-reverse' : 'flex-row']"
      >
        <!-- 头像 -->
        <div
          :class="[
            'w-7 h-7 rounded-lg shrink-0 flex items-center justify-center text-xs font-semibold mt-0.5',
            msg.role === 'user' ? 'bg-indigo-500/20 text-indigo-400' : 'bg-white/5 text-gray-400'
          ]"
        >
          {{ msg.role === 'user' ? 'U' : 'AI' }}
        </div>

        <!-- 气泡 -->
        <div
          :class="[
            'max-w-[72%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
            msg.role === 'user'
              ? 'bg-indigo-600/80 text-white rounded-tr-sm'
              : 'bg-white/[0.06] text-gray-200 rounded-tl-sm border border-white/[0.06]'
          ]"
        >
          <div v-if="msg.agentId" class="text-[10px] text-gray-500 mb-1 font-mono">{{ msg.agentId }}</div>
          <div v-if="msg.role === 'assistant'" class="prose prose-invert prose-sm max-w-none" v-html="marked.parse(msg.content) + (!msg.done ? '<span class=\'inline-block w-0.5 h-3.5 bg-gray-400 ml-0.5 animate-pulse align-text-bottom\'></span>' : '')"></div>
          <div v-else class="whitespace-pre-wrap">{{ msg.content }}</div>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="px-4 pb-4 shrink-0">
      <div class="flex items-end gap-2 bg-white/[0.04] border border-white/[0.08] rounded-2xl p-2 focus-within:border-white/20 transition-colors">
        <textarea
          v-model="input"
          class="flex-1 bg-transparent text-sm text-gray-200 placeholder-gray-600 resize-none outline-none leading-relaxed min-h-[40px] max-h-32 px-2 py-1.5"
          placeholder="输入碎片想法..."
          rows="1"
          @keydown="handleKeydown"
          @input="($event.target as HTMLTextAreaElement).style.height = 'auto'; ($event.target as HTMLTextAreaElement).style.height = ($event.target as HTMLTextAreaElement).scrollHeight + 'px'"
        />
        <button
          v-if="!streaming"
          :disabled="!input.trim()"
          class="w-8 h-8 rounded-xl flex items-center justify-center transition-all shrink-0"
          :class="input.trim() ? 'bg-indigo-600 hover:bg-indigo-500 text-white' : 'bg-white/5 text-gray-600 cursor-not-allowed'"
          @click="sendMessage"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </button>
        <button
          v-else
          class="w-8 h-8 rounded-xl bg-red-500/20 hover:bg-red-500/30 text-red-400 flex items-center justify-center transition-all shrink-0"
          @click="abortStream"
        >
          <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
            <rect x="6" y="6" width="12" height="12" rx="1" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>
