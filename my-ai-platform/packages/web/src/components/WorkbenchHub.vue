<script setup lang="ts">
import { computed } from "vue";
import { agentMeta } from "../shared/design-tokens";

const props = defineProps<{
  open: boolean;
  noteCount: number;
  trendCount: number;
  anomalyCount: number;
}>();

const emit = defineEmits<{
  close: [];
  navigate: [target: "trace" | "graph" | "profile" | "admin" | "digest"];
}>();

const attentionCount = computed(() => props.trendCount + props.anomalyCount);

const destinations = [
  {
    id: "trace" as const,
    key: "TR",
    title: "Trace Console",
    description: "核对 Agent 交接、策略门禁与执行证据",
    meta: "Live ledger",
  },
  {
    id: "graph" as const,
    key: "KG",
    title: "Knowledge Graph",
    description: "浏览笔记关系、冲突与演化链路",
    meta: "Explore",
  },
  {
    id: "profile" as const,
    key: "PF",
    title: "Knowledge Profile",
    description: "查看主题覆盖、思考习惯与 Agent 使用分布",
    meta: "Personal",
  },
  {
    id: "admin" as const,
    key: "OP",
    title: "Operations",
    description: "检查成本、模型健康与错误记录",
    meta: "System",
  },
];
</script>

<template>
  <Teleport to="body">
    <Transition name="hub">
      <div v-if="open" class="hub-layer" @mousedown.self="emit('close')">
        <section class="hub-panel" role="dialog" aria-modal="true" aria-label="Workbench Hub">
          <header class="hub-header">
            <div>
              <span class="eyebrow">Command center</span>
              <h2>Workbench Hub</h2>
            </div>
            <button class="close-button" title="关闭 Hub" aria-label="关闭 Hub" @click="emit('close')">×</button>
          </header>

          <div class="hub-summary">
            <button class="summary-cell" @click="emit('navigate', 'digest')">
              <strong>{{ noteCount }}</strong>
              <span>今日笔记</span>
            </button>
            <button class="summary-cell" @click="emit('navigate', 'digest')">
              <strong>{{ trendCount }}</strong>
              <span>趋势</span>
            </button>
            <button class="summary-cell" @click="emit('navigate', 'digest')">
              <strong :class="{ attention: anomalyCount > 0 }">{{ anomalyCount }}</strong>
              <span>异常</span>
            </button>
            <div class="summary-cell">
              <strong :class="{ attention: attentionCount > 0 }">{{ attentionCount }}</strong>
              <span>待关注</span>
            </div>
          </div>

          <div class="hub-body">
            <section class="hub-section">
              <div class="section-heading">
                <span>Workspace</span>
                <small>在一个位置进入所有系统视图</small>
              </div>
              <div class="destination-list">
                <button
                  v-for="item in destinations"
                  :key="item.id"
                  class="destination"
                  @click="emit('navigate', item.id)"
                >
                  <span class="destination-key">{{ item.key }}</span>
                  <span class="destination-copy">
                    <strong>{{ item.title }}</strong>
                    <small>{{ item.description }}</small>
                  </span>
                  <span class="destination-meta">{{ item.meta }} <b>›</b></span>
                </button>
              </div>
            </section>

            <aside class="agent-board">
              <div class="section-heading">
                <span>Routing policy</span>
                <small>显式 mention，外部路由器执行</small>
              </div>
              <div v-for="(agent, id) in agentMeta" :key="id" class="agent-row">
                <span class="agent-mark" :class="id">{{ agent.short }}</span>
                <div>
                  <strong>@{{ id }}</strong>
                  <small>{{ agent.role }}</small>
                </div>
                <span class="ready">Ready</span>
              </div>
              <p class="policy-note">
                Agent 在回答中写出明确的 @mention 后，路由层才会创建下一段任务并记录完整 trace。
              </p>
            </aside>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.hub-layer {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: start center;
  padding: 72px 24px 24px;
  background: rgba(3, 5, 8, 0.72);
  backdrop-filter: blur(10px);
}
.hub-panel {
  width: min(920px, 100%);
  max-height: calc(100vh - 96px);
  overflow: auto;
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  background: #11151a;
  box-shadow: 0 28px 90px rgba(0, 0, 0, 0.52);
}
.hub-header {
  min-height: 72px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-subtle);
}
.eyebrow, .section-heading span {
  display: block;
  color: var(--text-tertiary);
  font-size: 10px;
  font-weight: 750;
  text-transform: uppercase;
}
h2 { margin: 3px 0 0; font-size: 20px; }
.close-button {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 22px;
}
.close-button:hover { background: var(--surface-hover); color: var(--text-primary); }
.hub-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border-bottom: 1px solid var(--border-subtle);
  background: #0d1115;
}
.summary-cell {
  min-height: 68px;
  display: grid;
  align-content: center;
  gap: 3px;
  padding: 10px 18px;
  text-align: left;
  border-right: 1px solid var(--border-subtle);
}
button.summary-cell:hover { background: var(--surface-hover); }
.summary-cell:last-child { border-right: 0; }
.summary-cell strong { color: var(--text-primary); font-size: 19px; }
.summary-cell span { color: var(--text-tertiary); font-size: 11px; }
.summary-cell .attention { color: var(--color-warning); }
.hub-body { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(250px, .75fr); }
.hub-section, .agent-board { padding: 18px; }
.agent-board { border-left: 1px solid var(--border-subtle); background: #0e1216; }
.section-heading { margin-bottom: 12px; }
.section-heading small { display: block; margin-top: 4px; color: var(--text-tertiary); font-size: 11px; }
.destination-list { border: 1px solid var(--border-subtle); border-radius: 7px; overflow: hidden; }
.destination {
  width: 100%;
  min-height: 72px;
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 11px 13px;
  color: var(--text-primary);
  text-align: left;
  border-bottom: 1px solid var(--border-subtle);
}
.destination:last-child { border-bottom: 0; }
.destination:hover { background: var(--surface-hover); }
.destination-key, .agent-mark {
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  background: #202932;
  color: #9ccfe0;
  font-size: 10px;
  font-weight: 800;
}
.destination-copy { min-width: 0; display: grid; gap: 3px; }
.destination-copy strong { font-size: 13px; }
.destination-copy small { color: var(--text-tertiary); font-size: 11px; line-height: 1.4; }
.destination-meta { margin-left: auto; color: var(--text-tertiary); font-size: 10px; white-space: nowrap; }
.destination-meta b { margin-left: 5px; font-size: 16px; font-weight: 400; }
.agent-row {
  min-height: 54px;
  display: flex;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid var(--border-subtle);
}
.agent-mark.knowledge { color: var(--agent-knowledge); background: rgba(121,174,255,.10); }
.agent-mark.review { color: var(--agent-review); background: rgba(255,189,115,.10); }
.agent-mark.brain { color: var(--agent-brain); background: rgba(196,154,255,.10); }
.agent-row div { min-width: 0; display: grid; gap: 2px; }
.agent-row strong { font-size: 12px; }
.agent-row small { color: var(--text-tertiary); font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ready { margin-left: auto; color: var(--color-success); font-size: 9px; }
.policy-note { margin: 14px 0 0; color: var(--text-tertiary); font-size: 11px; line-height: 1.65; }
.hub-enter-active, .hub-leave-active { transition: opacity 160ms ease; }
.hub-enter-active .hub-panel, .hub-leave-active .hub-panel { transition: transform 180ms ease; }
.hub-enter-from, .hub-leave-to { opacity: 0; }
.hub-enter-from .hub-panel, .hub-leave-to .hub-panel { transform: translateY(-10px); }
@media (max-width: 720px) {
  .hub-layer { padding: 12px; }
  .hub-panel { max-height: calc(100vh - 24px); }
  .hub-body { grid-template-columns: 1fr; }
  .agent-board { border-left: 0; border-top: 1px solid var(--border-subtle); }
  .hub-summary { grid-template-columns: repeat(2, 1fr); }
  .summary-cell:nth-child(2) { border-right: 0; }
  .summary-cell:nth-child(-n+2) { border-bottom: 1px solid var(--border-subtle); }
}
</style>
