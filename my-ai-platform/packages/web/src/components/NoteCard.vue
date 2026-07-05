<script setup lang="ts">
interface Note {
  id: string;
  title: string;
  content: string;
  tags: string[];
  status: string;
  created_at: string;
}

const props = defineProps<{
  note: Note;
  selected: boolean;
}>();

const emit = defineEmits<{
  select: [note: Note];
  contextmenu: [e: MouseEvent, note: Note];
}>();

function formatRelative(s: string): string {
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  const now = Date.now();
  const diff = now - d.getTime();
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

const STATUS_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  live: { bg: "rgba(112,224,163,0.08)", text: "#70E0A3", border: "rgba(112,224,163,0.12)" },
  superseded: { bg: "rgba(255,184,107,0.08)", text: "#FFB86B", border: "rgba(255,184,107,0.12)" },
  archived: { bg: "rgba(154,164,178,0.06)", text: "#9AA4B2", border: "rgba(154,164,178,0.08)" },
};

const STATUS_LABEL: Record<string, string> = {
  live: "Live",
  superseded: "Superseded",
  archived: "Archived",
};

function handleClick() {
  emit("select", props.note);
}

function handleContextMenu(e: MouseEvent) {
  emit("contextmenu", e, props.note);
}
</script>

<template>
  <div
    class="group px-2.5 py-2 rounded-lg cursor-pointer transition-colors border mx-0.5 mb-0.5"
    :class="note.status === 'archived' ? 'opacity-50' : ''"
    :style="{
      background: selected ? 'rgba(124,156,255,0.08)' : 'transparent',
      borderColor: selected ? 'rgba(124,156,255,0.15)' : 'transparent',
    }"
    @click="handleClick"
    @contextmenu.prevent.stop="handleContextMenu"
  >
    <div class="flex items-start justify-between gap-1.5">
      <span class="text-xs leading-snug flex-1 line-clamp-2" style="color: #F4F6FA">{{ note.title }}</span>
      <span
        class="text-[8px] px-1 py-0.5 rounded-full font-medium shrink-0 mt-0.5 border"
        :style="{
          background: STATUS_STYLES[note.status]?.bg || STATUS_STYLES.live.bg,
          color: STATUS_STYLES[note.status]?.text || STATUS_STYLES.live.text,
          borderColor: STATUS_STYLES[note.status]?.border || STATUS_STYLES.live.border,
        }"
      >{{ STATUS_LABEL[note.status] || note.status }}</span>
    </div>
    <p v-if="note.content" class="text-[10px] mt-1 line-clamp-1 leading-relaxed" style="color: #9AA4B2; opacity: 0.7">
      {{ note.content.slice(0, 80) }}
    </p>
    <div class="flex items-center gap-2 mt-1.5">
      <div v-if="note.tags?.length" class="flex gap-1 flex-wrap flex-1">
        <span
          v-for="tag in note.tags.slice(0, 3)"
          :key="tag"
          class="text-[8px] px-1.5 py-0.5 rounded-full border"
          style="background: rgba(255,255,255,0.03); color: #9AA4B2; border-color: rgba(255,255,255,0.04)"
        >{{ tag }}</span>
      </div>
      <span class="text-[8px] shrink-0 ml-auto" style="color: #9AA4B2; opacity: 0.5">{{ formatRelative(note.created_at) }}</span>
    </div>
  </div>
</template>
