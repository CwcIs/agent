<script setup lang="ts">
const relatedNotes = [
  {
    title: "前端不是功能展示，而是能力显形",
    tag: "#product",
    reason: "这条笔记解释了为什么 Agent 和工具事件需要被收进更优雅的界面语言。",
  },
  {
    title: "多 Agent 不是自主路由",
    tag: "#agent",
    reason: "适合作为 Handoff Trace 的命名边界，避免把 prompt-chaining 说成自主路由。",
  },
  {
    title: "Daily Review 是留存入口",
    tag: "#retention",
    reason: "它把每日使用变成可回看的思考进展，而不是普通历史记录。",
  },
];

const recentNotes = [
  "前端交互为什么不像产品",
  "Agent 能力应该如何显形",
  "个人知识系统的记忆层",
  "ReviewAgent 的商用价值",
  "Daily Digest 的留存潜力",
];

const themes = ["前端交互", "商用及格线", "Agent 能力显形"];
</script>

<template>
  <div class="commercial-prototype min-h-screen overflow-hidden">
    <aside class="studio-rail">
      <div class="rail-brand">
        <div class="brand-mark">✦</div>
        <div>
          <div class="brand-title">Thought Studio</div>
          <div class="brand-subtitle">Personal AI workspace</div>
        </div>
      </div>

      <button class="new-thought">New Thought <span>⌘N</span></button>

      <nav class="rail-section">
        <div class="rail-label">Studio</div>
        <a class="rail-item active"><span>Inbox</span><em>12</em></a>
        <a class="rail-item"><span>Threads</span></a>
        <a class="rail-item"><span>Notes</span><em>86</em></a>
        <a class="rail-item"><span>Daily Review</span><i>3 themes</i></a>
        <a class="rail-item"><span>Archive</span></a>
      </nav>

      <div class="rail-section">
        <div class="rail-label">Agents</div>
        <div class="agent-pill knowledge"><span /> Knowledge</div>
        <div class="agent-pill review"><span /> Review</div>
        <div class="agent-pill brain"><span /> Brain</div>
      </div>

      <div class="rail-section rail-recent">
        <div class="rail-label">Recent Notes</div>
        <button v-for="note in recentNotes" :key="note">{{ note }}</button>
      </div>
    </aside>

    <main class="studio-main">
      <header class="studio-topbar">
        <div>
          <div class="crumb">Inbox / Product Experience</div>
          <h1>前端商用质感重构</h1>
        </div>
        <div class="topbar-actions">
          <button class="daily-chip">Today · 14 notes · 3 themes</button>
          <button class="cmd-chip">⌘K</button>
        </div>
      </header>

      <section class="thread-shell">
        <div class="thread-meta">
          <span class="live-dot" />
          <span>Live thread</span>
          <span>Knowledge → Review → Brain · natural_end</span>
        </div>

        <article class="thought-card user-card">
          <div class="block-label">Your Thought</div>
          <p>我感觉前端交互很一般，不够美观，也不具备商用的及格线。</p>
          <div class="block-footer">10:42 · captured from Studio Composer</div>
        </article>

        <article class="thought-card ai-card">
          <div class="response-head">
            <div>
              <div class="block-label">AI Response</div>
              <h2>判断是对的：问题不在能力，而在界面没有把能力变成体验。</h2>
            </div>
            <span class="response-badge">Studio Draft</span>
          </div>

          <p>
            当前后端已经有检索、挑战、联想和 handoff，但如果前端仍然像普通聊天流，
            用户只会看到“AI 又回复了一段文字”。商用改造的关键，是把复杂过程折叠成可点击的
            insight，同时让主工作区保持安静、聚焦、可信。
          </p>

          <div class="insight-row">
            <button>引用 3 条笔记</button>
            <button>Review 发现 2 个风险</button>
            <button>Brain 生成 4 个方向</button>
            <button>已保存为草稿</button>
          </div>

          <div class="agent-trace">
            <div class="trace-title">Agent Trace</div>
            <div class="trace-line">
              <span class="trace-node knowledge">Knowledge</span>
              <b />
              <span class="trace-node review">Review</span>
              <b />
              <span class="trace-node brain">Brain</span>
              <em>natural_end</em>
            </div>
          </div>
        </article>

        <section class="daily-panel">
          <div>
            <div class="block-label">Daily Signal</div>
            <strong>你今天的注意力正在从工程验收转向产品体验。</strong>
          </div>
          <div class="theme-list">
            <span v-for="theme in themes" :key="theme">{{ theme }}</span>
          </div>
        </section>
      </section>

      <section class="composer-wrap">
        <div class="suggestions">
          <span>Suggested</span>
          <button>保存为笔记</button>
          <button>让 Review 挑战</button>
          <button>让 Brain 发散</button>
        </div>
        <div class="composer">
          <textarea placeholder="写下一个想法、问题或碎片……" />
          <div class="composer-actions">
            <button>+ Attach</button>
            <button># Tag</button>
            <button>@ Agent</button>
            <div class="spacer" />
            <button class="secondary-action">Save</button>
            <button class="send-action">Send ↵</button>
          </div>
        </div>
      </section>
    </main>

    <aside class="insight-drawer">
      <div class="drawer-head">
        <div>
          <div class="block-label">Insight Drawer</div>
          <h3>Related Notes</h3>
        </div>
        <button>Esc</button>
      </div>

      <div class="drawer-card" v-for="note in relatedNotes" :key="note.title">
        <div class="note-top">
          <span>{{ note.tag }}</span>
          <em>Live</em>
        </div>
        <h4>{{ note.title }}</h4>
        <p>{{ note.reason }}</p>
        <div class="note-actions">
          <button>继续追问</button>
          <button>打开</button>
        </div>
      </div>

      <div class="drawer-card soft">
        <div class="block-label">Review Finding</div>
        <h4>隐藏假设</h4>
        <p>你可能把“后端能力完成”误当作“用户体验成立”。这正是前端需要补的断层。</p>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.commercial-prototype {
  --cp-bg: #0c0d12;
  --cp-panel: rgba(20, 22, 30, 0.82);
  --cp-panel-solid: #151821;
  --cp-card: rgba(255, 255, 255, 0.045);
  --cp-card-hover: rgba(255, 255, 255, 0.07);
  --cp-border: rgba(255, 255, 255, 0.085);
  --cp-border-strong: rgba(255, 255, 255, 0.15);
  --cp-text: #f4f1ea;
  --cp-muted: #a9a29a;
  --cp-faint: #706f78;
  --cp-brand: #8b7cff;
  --cp-brand-soft: rgba(139, 124, 255, 0.16);
  --cp-knowledge: #6ea8ff;
  --cp-review: #ffb86c;
  --cp-brain: #b892ff;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  position: relative;
  background:
    radial-gradient(circle at 52% -10%, rgba(139, 124, 255, 0.18), transparent 34%),
    radial-gradient(circle at 82% 18%, rgba(184, 146, 255, 0.12), transparent 24%),
    linear-gradient(135deg, #0b0c10 0%, #101118 52%, #0d0e13 100%);
  color: var(--cp-text);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

button, textarea {
  font: inherit;
}

button {
  color: inherit;
}

.studio-rail {
  border-right: 1px solid var(--cp-border);
  background: rgba(10, 11, 16, 0.56);
  backdrop-filter: blur(28px);
  padding: 22px 16px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.rail-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 2px 4px;
}

.brand-mark {
  width: 34px;
  height: 34px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, rgba(139, 124, 255, 0.95), rgba(184, 146, 255, 0.76));
  box-shadow: 0 14px 34px rgba(139, 124, 255, 0.28);
}

.brand-title {
  font-size: 14px;
  font-weight: 680;
  letter-spacing: -0.01em;
}

.brand-subtitle {
  color: var(--cp-faint);
  font-size: 11px;
  margin-top: 1px;
}

.new-thought {
  height: 42px;
  border: 1px solid rgba(139, 124, 255, 0.34);
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(139, 124, 255, 0.22), rgba(139, 124, 255, 0.09));
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 13px;
  font-size: 13px;
  font-weight: 620;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.new-thought span,
.cmd-chip {
  color: var(--cp-muted);
  font-size: 11px;
}

.rail-section {
  display: grid;
  gap: 6px;
}

.rail-label {
  color: var(--cp-faint);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 0 8px 4px;
}

.rail-item,
.rail-recent button {
  min-height: 34px;
  border: 1px solid transparent;
  border-radius: 11px;
  background: transparent;
  color: var(--cp-muted);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 9px;
  font-size: 13px;
  text-align: left;
}

.rail-item.active,
.rail-item:hover,
.rail-recent button:hover {
  background: rgba(255, 255, 255, 0.055);
  border-color: var(--cp-border);
  color: var(--cp-text);
}

.rail-item em,
.rail-item i {
  margin-left: auto;
  color: var(--cp-faint);
  font-style: normal;
  font-size: 11px;
}

.agent-pill {
  border: 1px solid var(--cp-border);
  border-radius: 999px;
  color: var(--cp-muted);
  background: rgba(255, 255, 255, 0.026);
  display: inline-flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  padding: 7px 11px;
  font-size: 12px;
}

.agent-pill span {
  width: 7px;
  height: 7px;
  border-radius: 999px;
}

.agent-pill.knowledge span { background: var(--cp-knowledge); }
.agent-pill.review span { background: var(--cp-review); }
.agent-pill.brain span { background: var(--cp-brain); }

.rail-recent {
  margin-top: auto;
}

.rail-recent button {
  width: 100%;
  line-height: 1.35;
  min-height: 38px;
}

.studio-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

.studio-topbar {
  height: 86px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 44px;
  border-bottom: 1px solid var(--cp-border);
  background: rgba(12, 13, 18, 0.42);
  backdrop-filter: blur(20px);
}

.crumb {
  color: var(--cp-faint);
  font-size: 12px;
  margin-bottom: 4px;
}

.studio-topbar h1 {
  font-size: 21px;
  line-height: 1.2;
  letter-spacing: -0.035em;
  margin: 0;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.daily-chip,
.cmd-chip {
  border: 1px solid var(--cp-border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  padding: 8px 12px;
  font-size: 12px;
}

.thread-shell {
  width: min(820px, calc(100% - 72px));
  margin: 34px auto 0;
  padding-bottom: 226px;
}

.thread-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--cp-faint);
  font-size: 12px;
  margin-bottom: 18px;
}

.live-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #70e0a3;
  box-shadow: 0 0 18px rgba(112, 224, 163, 0.62);
}

.thought-card,
.daily-panel {
  border: 1px solid var(--cp-border);
  border-radius: 24px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.058), rgba(255, 255, 255, 0.033));
  box-shadow:
    0 24px 80px rgba(0, 0, 0, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

.thought-card {
  padding: 24px;
  margin-bottom: 16px;
}

.user-card {
  background: rgba(255, 255, 255, 0.032);
}

.block-label {
  color: var(--cp-faint);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  margin-bottom: 10px;
}

.thought-card p {
  color: rgba(244, 241, 234, 0.9);
  font-size: 15.5px;
  line-height: 1.78;
  margin: 0;
}

.block-footer {
  color: var(--cp-faint);
  font-size: 11px;
  margin-top: 14px;
}

.response-head {
  display: flex;
  align-items: flex-start;
  gap: 18px;
  justify-content: space-between;
  margin-bottom: 18px;
}

.response-head h2 {
  font-size: 20px;
  line-height: 1.32;
  letter-spacing: -0.035em;
  max-width: 650px;
  margin: 0;
}

.response-badge {
  border: 1px solid rgba(139, 124, 255, 0.28);
  border-radius: 999px;
  background: var(--cp-brand-soft);
  color: #c8c1ff;
  white-space: nowrap;
  padding: 7px 10px;
  font-size: 11px;
}

.insight-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 22px;
}

.insight-row button {
  border: 1px solid var(--cp-border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--cp-muted);
  padding: 8px 11px;
  font-size: 12px;
  transition: 160ms ease;
}

.insight-row button:hover {
  background: var(--cp-card-hover);
  border-color: rgba(139, 124, 255, 0.34);
  color: var(--cp-text);
}

.agent-trace {
  margin-top: 20px;
  border: 1px solid var(--cp-border);
  border-radius: 18px;
  background: rgba(0, 0, 0, 0.14);
  padding: 14px;
}

.trace-title {
  color: var(--cp-faint);
  font-size: 11px;
  margin-bottom: 10px;
}

.trace-line {
  display: flex;
  align-items: center;
  gap: 10px;
}

.trace-line b {
  width: 24px;
  height: 1px;
  background: var(--cp-border-strong);
}

.trace-node {
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 11px;
  border: 1px solid var(--cp-border);
}

.trace-node.knowledge { color: var(--cp-knowledge); background: rgba(110, 168, 255, 0.1); }
.trace-node.review { color: var(--cp-review); background: rgba(255, 184, 108, 0.1); }
.trace-node.brain { color: var(--cp-brain); background: rgba(184, 146, 255, 0.1); }

.trace-line em {
  margin-left: auto;
  color: #70e0a3;
  font-style: normal;
  font-size: 11px;
}

.daily-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 18px 20px;
}

.daily-panel strong {
  font-size: 15px;
  line-height: 1.5;
}

.theme-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.theme-list span {
  border: 1px solid rgba(139, 124, 255, 0.23);
  border-radius: 999px;
  background: rgba(139, 124, 255, 0.1);
  color: #c8c1ff;
  padding: 7px 10px;
  font-size: 12px;
}

.composer-wrap {
  position: absolute;
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%);
  width: min(820px, calc(100% - 72px));
}

.suggestions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 10px 10px;
}

.suggestions span {
  color: var(--cp-faint);
  font-size: 11px;
}

.suggestions button,
.composer-actions button {
  border: 1px solid var(--cp-border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--cp-muted);
  padding: 7px 10px;
  font-size: 12px;
}

.composer {
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: 26px;
  background: rgba(23, 26, 36, 0.92);
  backdrop-filter: blur(28px);
  box-shadow:
    0 30px 90px rgba(0, 0, 0, 0.42),
    0 0 0 1px rgba(139, 124, 255, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.composer textarea {
  width: 100%;
  min-height: 78px;
  resize: none;
  outline: none;
  border: 0;
  background: transparent;
  color: var(--cp-text);
  padding: 18px 20px 8px;
  font-size: 15px;
  line-height: 1.6;
}

.composer textarea::placeholder {
  color: var(--cp-faint);
}

.composer-actions {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 10px 10px;
}

.composer-actions .spacer {
  flex: 1;
}

.composer-actions .secondary-action {
  color: #70e0a3;
  background: rgba(112, 224, 163, 0.08);
  border-color: rgba(112, 224, 163, 0.2);
}

.composer-actions .send-action {
  color: white;
  background: linear-gradient(135deg, var(--cp-brand), #a792ff);
  border-color: transparent;
  padding-inline: 14px;
}

.insight-drawer {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 392px;
  border-left: 1px solid var(--cp-border);
  background: rgba(14, 15, 21, 0.72);
  backdrop-filter: blur(30px);
  padding: 22px 18px;
  overflow: auto;
}

.drawer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
}

.drawer-head h3 {
  margin: 0;
  font-size: 18px;
  letter-spacing: -0.025em;
}

.drawer-head button {
  border: 1px solid var(--cp-border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--cp-faint);
  padding: 6px 9px;
  font-size: 11px;
}

.drawer-card {
  border: 1px solid var(--cp-border);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.045);
  padding: 16px;
  margin-bottom: 12px;
  transition: 160ms ease;
}

.drawer-card:hover {
  background: rgba(255, 255, 255, 0.065);
  border-color: rgba(139, 124, 255, 0.24);
}

.drawer-card.soft {
  background: rgba(255, 184, 108, 0.06);
  border-color: rgba(255, 184, 108, 0.15);
}

.note-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.note-top span {
  color: #c8c1ff;
  font-size: 11px;
}

.note-top em {
  color: #70e0a3;
  font-style: normal;
  font-size: 10px;
}

.drawer-card h4 {
  font-size: 14px;
  line-height: 1.45;
  margin: 0 0 8px;
}

.drawer-card p {
  color: var(--cp-muted);
  font-size: 12.5px;
  line-height: 1.65;
  margin: 0;
}

.note-actions {
  display: flex;
  gap: 8px;
  margin-top: 14px;
}

.note-actions button {
  border: 1px solid var(--cp-border);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--cp-muted);
  padding: 7px 9px;
  font-size: 11px;
}

@media (max-width: 1180px) {
  .commercial-prototype {
    grid-template-columns: 230px minmax(0, 1fr);
  }

  .insight-drawer {
    display: none;
  }
}

@media (max-width: 860px) {
  .commercial-prototype {
    grid-template-columns: minmax(0, 1fr);
  }

  .studio-rail {
    display: none;
  }

  .studio-topbar {
    height: auto;
    min-height: 82px;
    padding: 18px 22px;
    gap: 14px;
  }

  .studio-topbar h1 {
    font-size: 20px;
  }

  .daily-chip {
    display: none;
  }

  .thread-shell,
  .composer-wrap {
    width: calc(100% - 32px);
  }

  .thread-shell {
    margin-top: 22px;
    padding-bottom: 210px;
  }

  .thought-card {
    border-radius: 20px;
    padding: 20px;
  }

  .response-head {
    flex-direction: column;
    gap: 12px;
  }

  .response-head h2 {
    font-size: 19px;
  }

  .daily-panel {
    align-items: flex-start;
    flex-direction: column;
  }

  .theme-list {
    justify-content: flex-start;
  }
}
</style>
