<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { agentMeta } from "../shared/design-tokens";

interface ReviewCandidate {
  id: string;
  title: string;
  content: string;
  summary: string;
  tags: string[];
  origin_session_id: string;
  proposed_supersedes_id?: string | null;
  created_at: string;
}

type HubTab = "overview" | "review" | "routing";

const props = defineProps<{
  open: boolean;
  noteCount: number;
  trendCount: number;
  anomalyCount: number;
  pendingReviewCount: number;
}>();

const emit = defineEmits<{
  close: [];
  navigate: [target: "trace" | "graph" | "profile" | "admin" | "digest"];
  reviewUpdated: [];
}>();

const activeTab = ref<HubTab>("overview");
const candidates = ref<ReviewCandidate[]>([]);
const reviewLoading = ref(false);
const busyCandidateId = ref<string | null>(null);
const attentionCount = computed(() =>
  props.trendCount + props.anomalyCount + props.pendingReviewCount
);

const tabs: Array<{ id: HubTab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "review", label: "Review Queue" },
  { id: "routing", label: "Routing" },
];

const destinations = [
  { id: "trace" as const, key: "TR", title: "Trace Console", description: "核对 Agent 交接、策略门禁与执行证据", meta: "Live ledger" },
  { id: "graph" as const, key: "KG", title: "Knowledge Graph", description: "浏览笔记关系、冲突与演化链路", meta: "Explore" },
  { id: "profile" as const, key: "PF", title: "Knowledge Profile", description: "查看主题覆盖、思考习惯与 Agent 使用分布", meta: "Personal" },
  { id: "admin" as const, key: "OP", title: "Operations", description: "检查成本、模型健康与错误记录", meta: "System" },
];

async function loadCandidates() {
  reviewLoading.value = true;
  try {
    const response = await fetch("/notes?knowledge_status=pending_review");
    if (!response.ok) return;
    const data = await response.json();
    candidates.value = data.notes || [];
  } finally {
    reviewLoading.value = false;
  }
}

async function decideCandidate(candidateId: string, decision: "publish" | "reject") {
  busyCandidateId.value = candidateId;
  try {
    const response = await fetch(`/notes/${candidateId}/${decision}`, { method: "POST" });
    if (!response.ok) return;
    candidates.value = candidates.value.filter(candidate => candidate.id !== candidateId);
    emit("reviewUpdated");
  } finally {
    busyCandidateId.value = null;
  }
}

function candidatePreview(candidate: ReviewCandidate): string {
  return (candidate.summary || candidate.content).trim().slice(0, 220);
}

watch(
  () => props.open,
  open => {
    if (open) {
      activeTab.value = "overview";
      loadCandidates();
    }
  },
);
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

          <nav class="hub-tabs" aria-label="Hub views">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              :class="{ active: activeTab === tab.id }"
              @click="activeTab = tab.id"
            >
              {{ tab.label }}
              <span v-if="tab.id === 'review' && pendingReviewCount">{{ pendingReviewCount }}</span>
            </button>
          </nav>

          <div v-if="activeTab === 'overview'" class="hub-content">
            <div class="hub-summary">
              <button class="summary-cell" @click="emit('navigate', 'digest')"><strong>{{ noteCount }}</strong><span>今日笔记</span></button>
              <button class="summary-cell" @click="emit('navigate', 'digest')"><strong>{{ trendCount }}</strong><span>趋势</span></button>
              <button class="summary-cell" @click="activeTab = 'review'"><strong :class="{ attention: pendingReviewCount > 0 }">{{ pendingReviewCount }}</strong><span>待审核知识</span></button>
              <div class="summary-cell"><strong :class="{ attention: attentionCount > 0 }">{{ attentionCount }}</strong><span>待关注</span></div>
            </div>

            <section class="overview-section">
              <div class="section-heading">
                <span>Workspace</span>
                <small>在一个位置进入所有系统视图</small>
              </div>
              <div class="destination-list">
                <button v-for="item in destinations" :key="item.id" class="destination" @click="emit('navigate', item.id)">
                  <span class="destination-key">{{ item.key }}</span>
                  <span class="destination-copy"><strong>{{ item.title }}</strong><small>{{ item.description }}</small></span>
                  <span class="destination-meta">{{ item.meta }} <b>›</b></span>
                </button>
              </div>
            </section>
          </div>

          <div v-else-if="activeTab === 'review'" class="review-view">
            <header class="view-heading">
              <div><span>Human gate</span><h3>Candidate knowledge review</h3></div>
              <button title="刷新审批队列" aria-label="刷新审批队列" @click="loadCandidates">↻</button>
            </header>
            <div v-if="reviewLoading" class="empty-state">正在读取候选知识…</div>
            <div v-else-if="!candidates.length" class="empty-state">
              <strong>审批队列已清空</strong>
              <span>Agent 生成的知识会先进入这里，未经确认不会参与正式召回。</span>
            </div>
            <div v-else class="candidate-list">
              <article v-for="candidate in candidates" :key="candidate.id" class="candidate">
                <header>
                  <div>
                    <span class="candidate-type">{{ candidate.proposed_supersedes_id ? "SUPERSEDE" : "NEW KNOWLEDGE" }}</span>
                    <h4>{{ candidate.title }}</h4>
                  </div>
                  <time>{{ candidate.created_at }}</time>
                </header>
                <p>{{ candidatePreview(candidate) }}</p>
                <div v-if="candidate.tags?.length" class="tag-row">
                  <span v-for="tag in candidate.tags.slice(0, 5)" :key="tag">#{{ tag }}</span>
                </div>
                <footer>
                  <span v-if="candidate.origin_session_id">From task {{ candidate.origin_session_id.slice(0, 8) }}</span>
                  <div>
                    <button class="reject" :disabled="busyCandidateId === candidate.id" @click="decideCandidate(candidate.id, 'reject')">拒绝</button>
                    <button class="publish" :disabled="busyCandidateId === candidate.id" @click="decideCandidate(candidate.id, 'publish')">发布到知识库</button>
                  </div>
                </footer>
              </article>
            </div>
          </div>

          <div v-else class="routing-view">
            <div class="view-heading">
              <div><span>Prompt-chained handoff</span><h3>Routing policy</h3></div>
            </div>
            <div class="routing-grid">
              <article v-for="(agent, id) in agentMeta" :key="id" class="routing-agent">
                <span class="agent-mark" :class="id">{{ agent.short }}</span>
                <div><strong>@{{ id }}</strong><small>{{ agent.role }}</small></div>
                <span class="ready">Ready</span>
              </article>
            </div>
            <section class="policy-block">
              <span>Execution contract</span>
              <ol>
                <li>模型在输出中写出明确的 <code>@agent</code> mention。</li>
                <li>外部路由器解析目标，策略层完成深度、数量和风险检查。</li>
                <li>通过门禁后创建下一段任务，并把 proposal、decision、execution 写入 trace。</li>
              </ol>
            </section>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.hub-layer { position: fixed; inset: 0; z-index: 80; display: grid; place-items: start center; padding: 58px 24px 24px; background: rgba(3,5,8,.72); backdrop-filter: blur(10px); }
.hub-panel { width: min(920px, 100%); max-height: calc(100vh - 82px); overflow: auto; border: 1px solid var(--border-strong); border-radius: 8px; background: #11151a; box-shadow: 0 28px 90px rgba(0,0,0,.52); }
.hub-header { min-height: 66px; display: flex; align-items: center; justify-content: space-between; padding: 12px 18px; border-bottom: 1px solid var(--border-subtle); }
.eyebrow, .section-heading span, .view-heading span, .policy-block > span { display: block; color: var(--text-tertiary); font-size: 9px; font-weight: 750; text-transform: uppercase; }
h2 { margin: 3px 0 0; font-size: 19px; }
.close-button { width: 32px; height: 32px; border-radius: 6px; color: var(--text-secondary); font-size: 22px; }
.close-button:hover { background: var(--surface-hover); color: var(--text-primary); }
.hub-tabs { height: 42px; display: flex; align-items: end; gap: 4px; padding: 0 14px; border-bottom: 1px solid var(--border-subtle); background: #0d1115; }
.hub-tabs button { height: 37px; display: flex; align-items: center; gap: 7px; padding: 0 11px; border-bottom: 2px solid transparent; color: var(--text-tertiary); font-size: 10px; }
.hub-tabs button:hover { color: var(--text-primary); }
.hub-tabs button.active { border-color: #79bdcb; color: var(--text-primary); }
.hub-tabs button span { min-width: 17px; height: 17px; display: grid; place-items: center; border-radius: 50%; background: rgba(255,189,115,.14); color: var(--agent-review); font-size: 8px; }
.hub-summary { display: grid; grid-template-columns: repeat(4,1fr); border-bottom: 1px solid var(--border-subtle); }
.summary-cell { min-height: 64px; display: grid; align-content: center; gap: 3px; padding: 9px 18px; border-right: 1px solid var(--border-subtle); color: var(--text-primary); text-align: left; }
button.summary-cell:hover { background: var(--surface-hover); }
.summary-cell:last-child { border-right: 0; }
.summary-cell strong { font-size: 18px; }
.summary-cell span { color: var(--text-tertiary); font-size: 10px; }
.summary-cell .attention { color: var(--color-warning); }
.overview-section, .review-view, .routing-view { padding: 18px; }
.section-heading { margin-bottom: 11px; }
.section-heading small { display: block; margin-top: 4px; color: var(--text-tertiary); font-size: 10px; }
.destination-list { border: 1px solid var(--border-subtle); border-radius: 7px; overflow: hidden; }
.destination { width: 100%; min-height: 66px; display: flex; align-items: center; gap: 13px; padding: 10px 13px; border-bottom: 1px solid var(--border-subtle); color: var(--text-primary); text-align: left; }
.destination:last-child { border-bottom: 0; }
.destination:hover { background: var(--surface-hover); }
.destination-key, .agent-mark { width: 30px; height: 30px; flex: 0 0 30px; display: grid; place-items: center; border-radius: 6px; background: #202932; color: #9ccfe0; font-size: 9px; font-weight: 800; }
.destination-copy { min-width: 0; display: grid; gap: 3px; }
.destination-copy strong { font-size: 12px; }
.destination-copy small { color: var(--text-tertiary); font-size: 10px; }
.destination-meta { margin-left: auto; color: var(--text-tertiary); font-size: 9px; white-space: nowrap; }
.destination-meta b { margin-left: 5px; font-size: 15px; font-weight: 400; }
.view-heading { min-height: 48px; display: flex; align-items: start; justify-content: space-between; border-bottom: 1px solid var(--border-subtle); }
.view-heading h3 { margin: 4px 0 0; color: var(--text-primary); font-size: 15px; }
.view-heading button { width: 30px; height: 30px; border-radius: 5px; color: var(--text-secondary); font-size: 17px; }
.view-heading button:hover { background: var(--surface-hover); color: var(--text-primary); }
.candidate-list { display: grid; gap: 8px; margin-top: 12px; }
.candidate { padding: 13px; border: 1px solid var(--border-subtle); border-radius: 7px; background: #0e1318; }
.candidate > header { display: flex; justify-content: space-between; gap: 12px; }
.candidate-type { color: var(--agent-review); font-size: 8px; font-weight: 800; }
.candidate h4 { margin: 4px 0 0; color: var(--text-primary); font-size: 13px; }
.candidate time { color: var(--text-tertiary); font-size: 9px; white-space: nowrap; }
.candidate p { margin: 10px 0; color: var(--text-secondary); font-size: 11px; line-height: 1.65; }
.tag-row { display: flex; flex-wrap: wrap; gap: 5px; }
.tag-row span { color: #8abec9; font-size: 9px; }
.candidate footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-subtle); color: var(--text-tertiary); font-size: 9px; }
.candidate footer div { display: flex; gap: 7px; }
.candidate footer button { min-height: 29px; padding: 0 10px; border: 1px solid var(--border-subtle); border-radius: 5px; font-size: 10px; }
.candidate footer button:disabled { opacity: .45; }
.candidate .reject { color: var(--text-secondary); }
.candidate .publish { border-color: #31515c; background: #17272d; color: #bfe4eb; }
.empty-state { min-height: 260px; display: grid; place-content: center; justify-items: center; gap: 7px; color: var(--text-tertiary); font-size: 11px; text-align: center; }
.empty-state strong { color: var(--text-secondary); font-size: 13px; }
.routing-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 8px; margin-top: 12px; }
.routing-agent { min-height: 70px; display: flex; align-items: center; gap: 10px; padding: 10px; border: 1px solid var(--border-subtle); border-radius: 7px; background: #0e1318; }
.agent-mark.knowledge { color: var(--agent-knowledge); background: rgba(121,174,255,.10); }
.agent-mark.review { color: var(--agent-review); background: rgba(255,189,115,.10); }
.agent-mark.brain { color: var(--agent-brain); background: rgba(196,154,255,.10); }
.routing-agent div { min-width: 0; display: grid; gap: 3px; }
.routing-agent strong { font-size: 11px; }
.routing-agent small { overflow: hidden; color: var(--text-tertiary); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.ready { margin-left: auto; color: var(--color-success); font-size: 8px; }
.policy-block { margin-top: 16px; padding: 14px; border-left: 2px solid #31515c; background: #0e1318; }
.policy-block ol { margin: 9px 0 0; padding-left: 18px; color: var(--text-secondary); font-size: 10px; line-height: 1.8; }
.policy-block code { color: #a8dce6; }
.hub-enter-active, .hub-leave-active { transition: opacity 160ms ease; }
.hub-enter-active .hub-panel, .hub-leave-active .hub-panel { transition: transform 180ms ease; }
.hub-enter-from, .hub-leave-to { opacity: 0; }
.hub-enter-from .hub-panel, .hub-leave-to .hub-panel { transform: translateY(-10px); }
@media (max-width: 720px) {
  .hub-layer { padding: 10px; }
  .hub-panel { max-height: calc(100vh - 20px); }
  .hub-summary { grid-template-columns: repeat(2,1fr); }
  .summary-cell:nth-child(2) { border-right: 0; }
  .summary-cell:nth-child(-n+2) { border-bottom: 1px solid var(--border-subtle); }
  .routing-grid { grid-template-columns: 1fr; }
  .candidate footer { align-items: flex-start; flex-direction: column; }
  .candidate footer div { width: 100%; justify-content: flex-end; }
}
</style>
