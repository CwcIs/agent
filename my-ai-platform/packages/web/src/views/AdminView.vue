<script setup lang="ts">
import { ref, onMounted } from "vue";

interface AdminStats {
  notes: { total: number; live: number; edges: number; collisions: number };
  costs: { today_calls: number; today_cost_usd: number; week_calls: number; week_cost_usd: number };
  models: Array<{ model: string; calls: number; cost_usd: number }>;
  agents: Array<{ agent: string; calls: number }>;
  errors_today: number;
  db_size_mb: number;
}

const stats = ref<AdminStats | null>(null);
const errors = ref<Array<any>>([]);
const health = ref<any>(null);
const loading = ref(true);
const activeTab = ref<"overview" | "errors" | "health">("overview");

onMounted(async () => {
  try {
    const [statsResp, errorsResp, healthResp] = await Promise.all([
      fetch("/admin/stats"),
      fetch("/admin/errors?limit=30"),
      fetch("/admin/health"),
    ]);
    if (statsResp.ok) stats.value = await statsResp.json();
    if (errorsResp.ok) {
      const data = await errorsResp.json();
      errors.value = data.errors || [];
    }
    if (healthResp.ok) health.value = await healthResp.json();
  } catch { /* ignore */ }
  loading.value = false;
});
</script>

<template>
  <div class="h-full flex flex-col overflow-y-auto" style="background: var(--bg-app)">
    <div class="flex items-center px-6 py-4 border-b shrink-0" style="border-color: var(--border-subtle)">
      <h2 class="text-lg font-semibold" style="color: var(--text-main)">Admin Panel</h2>
    </div>

    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <span class="text-sm" style="color: var(--text-muted)">Loading...</span>
    </div>

    <div v-else class="flex-1 p-6 space-y-4 overflow-y-auto">
      <!-- Tabs -->
      <div class="flex gap-2">
        <button v-for="tab in (['overview','errors','health'] as const)" :key="tab"
          class="text-[11px] px-3 py-1 rounded-full border transition-all"
          :style="{
            background: activeTab === tab ? 'rgba(255,255,255,0.06)' : 'transparent',
            color: activeTab === tab ? 'var(--text-main)' : 'var(--text-tertiary)',
            borderColor: activeTab === tab ? 'rgba(255,255,255,0.1)' : 'transparent',
          }"
          @click="activeTab = tab"
        >{{ { overview: 'Overview', errors: 'Errors', health: 'Health' }[tab] }}</button>
      </div>

      <!-- Overview -->
      <div v-if="activeTab === 'overview' && stats" class="space-y-4">
        <div class="grid grid-cols-4 gap-3">
          <div class="stat-card">
            <span class="text-lg font-semibold" style="color: var(--text-main)">{{ stats.notes.live }}</span>
            <span class="text-[10px]" style="color: var(--text-tertiary)">Live Notes</span>
          </div>
          <div class="stat-card">
            <span class="text-lg font-semibold" style="color: var(--text-main)">{{ stats.notes.edges }}</span>
            <span class="text-[10px]" style="color: var(--text-tertiary)">Edges</span>
          </div>
          <div class="stat-card">
            <span class="text-lg font-semibold" style="color: var(--text-main)">{{ stats.notes.collisions }}</span>
            <span class="text-[10px]" style="color: var(--text-tertiary)">Collisions</span>
          </div>
          <div class="stat-card">
            <span class="text-lg font-semibold" style="color: var(--text-main)">{{ stats.db_size_mb }} MB</span>
            <span class="text-[10px]" style="color: var(--text-tertiary)">DB Size</span>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div class="section-card">
            <h3 class="text-[11px] font-semibold mb-3" style="color: var(--text-muted)">COSTS</h3>
            <div class="space-y-2 text-[11px]">
              <div class="flex justify-between"><span style="color: var(--text-muted)">Today</span><span style="color: var(--text-main)">${{ stats.costs.today_cost_usd.toFixed(4) }} ({{ stats.costs.today_calls }} calls)</span></div>
              <div class="flex justify-between"><span style="color: var(--text-muted)">This Week</span><span style="color: var(--text-main)">${{ stats.costs.week_cost_usd.toFixed(4) }} ({{ stats.costs.week_calls }} calls)</span></div>
              <div class="flex justify-between"><span style="color: var(--text-muted)">Today Errors</span><span :style="{ color: stats.errors_today > 0 ? 'var(--color-warning)' : 'var(--text-main)' }">{{ stats.errors_today }}</span></div>
            </div>
          </div>

          <div class="section-card">
            <h3 class="text-[11px] font-semibold mb-3" style="color: var(--text-muted)">BY PROVIDER</h3>
            <div v-for="m in stats.models" :key="m.model" class="flex justify-between text-[11px] py-0.5">
              <span style="color: var(--text-muted)">{{ m.model }}</span>
              <span style="color: var(--text-tertiary)">{{ m.calls }} calls · ${{ m.cost_usd.toFixed(4) }}</span>
            </div>
          </div>
        </div>

        <div class="section-card">
          <h3 class="text-[11px] font-semibold mb-3" style="color: var(--text-muted)">BY AGENT</h3>
          <div class="flex gap-4">
            <div v-for="a in stats.agents" :key="a.agent" class="text-[11px] px-3 py-1.5 rounded-lg" style="background: rgba(255,255,255,0.03)">
              <span style="color: var(--text-main); font-weight: 500">{{ a.agent }}</span>
              <span style="color: var(--text-tertiary); margin-left: 6px">{{ a.calls }} calls</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Errors -->
      <div v-if="activeTab === 'errors'" class="space-y-2">
        <div v-if="errors.length === 0" class="text-sm" style="color: var(--text-muted)">No errors recorded.</div>
        <div v-for="e in errors" :key="e.id" class="text-[11px] p-3 rounded-lg border" style="border-color: var(--border-subtle); background: rgba(255,255,255,0.02)">
          <div class="flex justify-between mb-1">
            <span style="color: var(--color-warning); font-weight: 500">{{ e.error_type }}</span>
            <span style="color: var(--text-tertiary)">{{ e.agent_id }} · {{ e.model }} · {{ e.created_at }}</span>
          </div>
          <div style="color: var(--text-muted); max-height: 60px; overflow: hidden">{{ e.error_msg }}</div>
        </div>
      </div>

      <!-- Health -->
      <div v-if="activeTab === 'health' && health" class="space-y-3">
        <div class="section-card">
          <h3 class="text-[11px] font-semibold mb-2" style="color: var(--text-muted)">VECTOR MODEL</h3>
          <div class="text-[11px] space-y-1">
            <div class="flex justify-between"><span style="color: var(--text-muted)">Status</span><span :style="{ color: health.vector_model.status === 'ok' ? '#70E0A3' : 'var(--color-warning)' }">{{ health.vector_model.status }}</span></div>
            <div class="flex justify-between"><span style="color: var(--text-muted)">Coverage</span><span style="color: var(--text-main)">{{ health.vector_model.coverage_pct }}%</span></div>
          </div>
        </div>
        <div class="section-card">
          <h3 class="text-[11px] font-semibold mb-2" style="color: var(--text-muted)">LLM PROVIDERS</h3>
          <div class="text-[11px] space-y-1">
            <div v-for="(status, provider) in health.providers" :key="provider" class="flex justify-between">
              <span style="color: var(--text-muted)">{{ provider }}</span>
              <span :style="{ color: status === 'ok' ? '#70E0A3' : 'var(--color-warning)' }">{{ status }}</span>
            </div>
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
.section-card {
  padding: 14px;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: rgba(255,255,255,0.02);
}
</style>
