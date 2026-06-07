<script setup lang="ts">
/**
 * 每日 AI 回顾摘要面板
 * 对应 MD §2 场景 D — 用户每天首次打开的第一屏
 *
 * 显示：昨天写了 N 条笔记 + AI 连贯综述 + 恰好 3 条追问
 */
import { ref, onMounted } from "vue";

interface Digest {
  date: string;
  noteCount: number;
  narrative: string;
  followUps: string[];
  citedNotes: Array<{ noteId: string; title: string }>;
}

const digest = ref<Digest | null>(null);
const loading = ref(true);

onMounted(async () => {
  try {
    const resp = await fetch("/digest");
    digest.value = await resp.json();
  } catch (e) {
    digest.value = null;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div v-if="loading" class="bg-white border-b p-4 text-sm text-gray-400">
    正在生成今日回顾...
  </div>

  <div v-else-if="digest" class="bg-white border-b p-4">
    <h3 class="text-sm font-semibold text-gray-500 mb-2">
      📊 {{ digest.date }} 回顾 · {{ digest.noteCount }} 条笔记
    </h3>
    <p class="text-sm text-gray-700 leading-relaxed mb-3">
      {{ digest.narrative }}
    </p>
    <div v-if="digest.followUps.length" class="border-t pt-2">
      <p class="text-xs font-medium text-gray-500 mb-1">值得追问：</p>
      <ul class="space-y-1">
        <li
          v-for="(q, i) in digest.followUps"
          :key="i"
          class="text-sm text-blue-600 cursor-pointer hover:underline"
          @click="$emit('followUp', q)"
        >
          {{ i + 1 }}. {{ q }}
        </li>
      </ul>
    </div>
  </div>

  <div v-else class="bg-white border-b p-4 text-sm text-gray-400">
    暂无回顾数据，先去写笔记吧 ✍️
  </div>
</template>
