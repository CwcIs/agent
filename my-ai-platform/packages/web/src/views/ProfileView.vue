<script setup lang="ts">
import { ref, onMounted } from "vue";

interface UserProfile {
  interests: Array<{ tag: string; count: number }>;
  peak_hours: Array<{ hour: number; count: number }>;
  active_days: Array<{ day: string; count: number }>;
  thinking_style: {
    analytical: number;
    divergent: number;
    practical: number;
    label: string;
  };
  knowledge_coverage: {
    dimensions: Record<string, { note_count: number; level: string }>;
    total_dimensions_with_content: number;
  };
  agent_usage: Array<{ agent: string; calls: number; cost_usd: number }>;
  notes: {
    live: number;
    archived: number;
    superseded: number;
    edges: number;
    collisions: number;
  };
  note_timeline: Array<{ month: string; count: number }>;
  cost: { total_usd: number; total_calls: number };
}

const profile = ref<UserProfile | null>(null);
const loading = ref(true);
const error = ref("");

const agentLabels: Record<string, string> = {
  knowledge: "Knowledge",
  review: "Review",
  brain: "Brain",
};

const levelColors: Record<string, string> = {
  "丰富": "#70E0A3",
  "有涉猎": "#FFB86B",
  "空白": "var(--text-tertiary)",
};

onMounted(async () => {
  try {
    const resp = await fetch("/user/profile");
    if (resp.ok) {
      profile.value = await resp.json();
    } else {
      error.value = "Failed to load profile";
    }
  } catch {
    error.value = "Network error";
  } finally {
    loading.value = false;
  }
});

function exportNotes(fmt: string) {
  window.open(`/notes/export?fmt=${fmt}`, "_blank");
}
</script>

<template>
  <div class="h-full flex flex-col overflow-y-auto" style="background: var(--bg-app)">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-4 border-b shrink-0" style="border-color: var(--border-subtle)">
      <div>
        <h2 class="text-lg font-semibold" style="color: var(--text-main)">My Knowledge Profile</h2>
        <p class="text-[11px] mt-0.5" style="color: var(--text-tertiary)">Your thinking patterns, interests, and knowledge landscape</p>
      </div>
      <div class="flex gap-2">
        <button class="text-[10px] px-2.5 py-1 rounded-lg border transition-all hover:brightness-110"
          style="border-color: var(--border-subtle); color: var(--text-muted)"
          @click="exportNotes('markdown')">Export MD</button>
        <button class="text-[10px] px-2.5 py-1 rounded-lg border transition-all hover:brightness-110"
          style="border-color: var(--border-subtle); color: var(--text-muted)"
          @click="exportNotes('json')">Export JSON</button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <div class="w-2 h-2 rounded-full animate-pulse-glow" style="background: var(--agent-knowledge)" />
    </div>

    <!-- Error -->
    <div v-else-if="error || !profile" class="flex-1 flex items-center justify-center">
      <span class="text-sm" style="color: var(--text-muted)">{{ error || 'No profile data' }}</span>
    </div>

    <!-- Content -->
    <div v-else class="flex-1 p-6 space-y-5 overflow-y-auto">
      <!-- Top Stats -->
      <div class="grid grid-cols-4 gap-3">
        <div class="stat-card">
          <span class="stat-value">{{ profile.notes.live }}</span>
          <span class="stat-label">Live Notes</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ profile.notes.edges }}</span>
          <span class="stat-label">Relations</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ profile.notes.collisions }}</span>
          <span class="stat-label">Collisions</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">${{ profile.cost.total_usd.toFixed(3) }}</span>
          <span class="stat-label">{{ profile.cost.total_calls }} LLM calls</span>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-4">
        <!-- Thinking Style -->
        <div class="section-card">
          <h3 class="section-title">Thinking Style</h3>
          <div class="text-sm font-medium mb-3" style="color: var(--agent-knowledge)">{{ profile.thinking_style.label }}</div>
          <div class="space-y-2">
            <div v-for="(val, key) in profile.thinking_style" :key="key" v-show="typeof val === 'number'">
              <div class="flex justify-between text-[11px] mb-0.5">
                <span style="color: var(--text-muted)">{{ { analytical: 'Analytical', divergent: 'Divergent', practical: 'Practical' }[key] || key }}</span>
                <span style="color: var(--text-tertiary)">{{ (val as number * 100).toFixed(0) }}%</span>
              </div>
              <div class="h-1 rounded-full" style="background: rgba(255,255,255,0.05)">
                <div class="h-1 rounded-full transition-all" :style="{ width: (val as number * 100) + '%', background: key === 'analytical' ? 'var(--agent-knowledge)' : key === 'divergent' ? 'var(--agent-brain)' : '#70E0A3' }" />
              </div>
            </div>
          </div>
        </div>

        <!-- Active Hours -->
        <div class="section-card">
          <h3 class="section-title">Active Hours</h3>
          <div v-if="profile.peak_hours.length" class="space-y-1.5">
            <div v-for="ph in profile.peak_hours" :key="ph.hour" class="flex items-center gap-2 text-[11px]">
              <span class="w-12 shrink-0" style="color: var(--text-muted)">{{ String(ph.hour).padStart(2, '0') }}:00</span>
              <div class="flex-1 h-1.5 rounded-full" style="background: rgba(255,255,255,0.04)">
                <div class="h-1.5 rounded-full" :style="{ width: (ph.count / profile.peak_hours[0].count * 100) + '%', background: 'var(--agent-knowledge)' }" />
              </div>
              <span class="w-8 text-right" style="color: var(--text-tertiary)">{{ ph.count }}</span>
            </div>
          </div>
          <div v-if="profile.active_days.length" class="mt-3">
            <span class="text-[10px]" style="color: var(--text-tertiary)">Most active days: </span>
            <span v-for="(ad, i) in profile.active_days" :key="ad.day" class="text-[10px]">
              <span style="color: var(--text-muted)">{{ ad.day }}</span>
              <span v-if="i < profile.active_days.length - 1" style="color: var(--text-tertiary)">, </span>
            </span>
          </div>
        </div>
      </div>

      <!-- Interests -->
      <div class="section-card">
        <h3 class="section-title">Top Interests</h3>
        <div class="flex flex-wrap gap-2">
          <span v-for="int in profile.interests" :key="int.tag"
            class="text-[11px] px-2.5 py-1 rounded-full border"
            :style="{ background: 'rgba(124,156,255,0.06)', borderColor: 'rgba(124,156,255,0.15)', color: 'var(--agent-knowledge)' }">
            {{ int.tag }} <span style="opacity: 0.5">×{{ int.count }}</span>
          </span>
        </div>
      </div>

      <!-- Knowledge Coverage -->
      <div class="section-card">
        <h3 class="section-title">Knowledge Coverage</h3>
        <div class="grid grid-cols-2 gap-2">
          <div v-for="(info, dim) in profile.knowledge_coverage.dimensions" :key="dim"
            class="flex items-center justify-between text-[11px] px-3 py-2 rounded-lg"
            style="background: rgba(255,255,255,0.02)">
            <span style="color: var(--text-muted)">{{ dim }}</span>
            <div class="flex items-center gap-2">
              <span style="color: var(--text-tertiary)">{{ info.note_count }} notes</span>
              <span class="text-[10px] px-1.5 py-0.5 rounded-full" :style="{ background: 'rgba(255,255,255,0.04)', color: levelColors[info.level] || 'var(--text-tertiary)' }">
                {{ info.level }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Agent Usage -->
      <div class="section-card">
        <h3 class="section-title">Agent Usage</h3>
        <div class="space-y-1.5">
          <div v-for="au in profile.agent_usage" :key="au.agent" class="flex items-center gap-3 text-[11px]">
            <span class="w-20 shrink-0" style="color: var(--text-muted)">{{ agentLabels[au.agent] || au.agent }}</span>
            <div class="flex-1 h-1.5 rounded-full" style="background: rgba(255,255,255,0.04)">
              <div class="h-1.5 rounded-full" :style="{
                width: (au.calls / profile.agent_usage[0].calls * 100) + '%',
                background: au.agent === 'knowledge' ? 'var(--agent-knowledge)' : au.agent === 'review' ? 'var(--agent-review)' : 'var(--agent-brain)'
              }" />
            </div>
            <span class="w-16 text-right" style="color: var(--text-tertiary)">{{ au.calls }} calls</span>
            <span class="w-14 text-right" style="color: var(--text-tertiary)">${{ au.cost_usd.toFixed(3) }}</span>
          </div>
        </div>
      </div>

      <!-- Note Timeline -->
      <div class="section-card" v-if="profile.note_timeline.length">
        <h3 class="section-title">Note Timeline (12 months)</h3>
        <div class="flex items-end gap-1 h-16">
          <div v-for="m in [...profile.note_timeline].reverse()" :key="m.month" class="flex-1 flex flex-col items-center gap-1">
            <span class="text-[9px]" style="color: var(--text-tertiary)">{{ m.count || '' }}</span>
            <div class="w-full rounded-t-sm transition-all" :style="{
              height: Math.max(2, (m.count / Math.max(...profile.note_timeline.map(x => x.count), 1) * 48)) + 'px',
              background: 'var(--agent-knowledge)', opacity: 0.3 + (m.count / Math.max(...profile.note_timeline.map(x => x.count), 1) * 0.7)
            }" />
            <span class="text-[8px]" style="color: var(--text-tertiary)">{{ m.month.slice(5) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stat-card {
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: rgba(255,255,255,0.02);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-main);
}
.stat-label {
  font-size: 10px;
  color: var(--text-tertiary);
}
.section-card {
  padding: 16px;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: rgba(255,255,255,0.02);
}
.section-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin-bottom: 10px;
}
</style>
