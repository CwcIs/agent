<script setup lang="ts">
/**
 * Chat 界面 — SSE 流式响应 + Agent 切换通知
 * 对应 MD §5.3 + 附录图 5（场景 A 数据流）
 */
import { ref, onUnmounted } from "vue";

const messages = ref<Array<{ role: string; content: string; agentId?: string }>>([]);
const input = ref("");
const streaming = ref(false);
let eventSource: EventSource | null = null;

function sendMessage() {
  if (!input.value.trim() || streaming.value) return;

  messages.value.push({ role: "user", content: input.value });
  streaming.value = true;

  const encoded = encodeURIComponent(input.value);
  eventSource = new EventSource(`/chat/stream?input=${encoded}`);

  eventSource.addEventListener("text", (e) => {
    const data = JSON.parse(e.data);
    const last = messages.value[messages.value.length - 1];
    if (last?.role === "assistant") {
      last.content += data.delta;
    } else {
      messages.value.push({ role: "assistant", content: data.delta, agentId: data.agentId });
    }
  });

  eventSource.addEventListener("agent_switch", (e) => {
    const data = JSON.parse(e.data);
    // 显示 Agent 切换动画
  });

  eventSource.addEventListener("done", () => {
    streaming.value = false;
    eventSource?.close();
  });

  eventSource.onerror = () => {
    streaming.value = false;
    eventSource?.close();
  };

  input.value = "";
}

function abortStream() {
  eventSource?.close();
  streaming.value = false;
}

onUnmounted(() => {
  eventSource?.close();
});
</script>

<template>
  <div class="flex-1 flex flex-col p-4">
    <!-- 消息列表 -->
    <div class="flex-1 overflow-y-auto space-y-4 mb-4">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        :class="[
          'max-w-2xl rounded-lg p-3',
          msg.role === 'user'
            ? 'bg-blue-500 text-white ml-auto'
            : 'bg-white border mr-auto',
        ]"
      >
        <div v-if="msg.agentId" class="text-xs text-gray-400 mb-1">
          {{ msg.agentId }}
        </div>
        <div class="whitespace-pre-wrap">{{ msg.content }}</div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="flex gap-2">
      <textarea
        v-model="input"
        class="flex-1 border rounded-lg p-3 resize-none"
        rows="2"
        placeholder="输入碎片想法，AI 帮你整理成结构化笔记..."
        @keydown.enter.exact.prevent="sendMessage"
      />
      <button
        v-if="!streaming"
        class="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
        @click="sendMessage"
      >
        发送
      </button>
      <button
        v-else
        class="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600"
        @click="abortStream"
      >
        中断
      </button>
    </div>
  </div>
</template>
