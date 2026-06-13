# 个人 Multi-Agent 知识工作台

> Claude 项目上下文文件。完整设计文档见 [MY-AI-PLATFORM_1.md](MY-AI-PLATFORM_1.md)（2298 行）。

## 项目本质

帮我把**碎片想法 → 结构化笔记**，让 AI 帮我连接、检索、挑战自己的思考。

两个核心机制（[MD §3.0](MY-AI-PLATFORM_1.md)）：
1. **ReAct Tool Loop**（单 Agent 内）— 模型自主决定调用工具
2. **Prompt-Chained Handoff**（跨 Agent）— 模型在输出写 `@gpt`，路由器字符串匹配后调度

**关键认知**：第二个不是"Agent 自主路由"，是 prompt 里教模型写 `@x` + 外部 30 行正则代码。

## 当前状态：Phase 1 ✅ → Phase 2（进行中）

**Phase 1**（2026-06-02 ~ 06-09）— [retro](my-ai-platform/docs/retro/phase1-retro.md) ✅ 全部验收通过

**Phase 2 范围**（进行中，已有突破）：
- ✅ 向量检索：sqlite-vec + sentence-transformers（`d94a0a2`）
- ✅ A2A 架构：Agent 注册表 + 路由循环 + `@agent` mention（`ad6df62`）
- ✅ ReviewAgent：prompt-chained thought challenger（`a4259bb`）
- ✅ 笔记编辑/删除/归档：DELETE + PATCH `/notes/:id`（`24253b8`）
- ✅ 跨笔记合成：`synthesize_notes` 工具（`0cdeb09`）
- ✅ `#hashtag` 显式路由：`#review` 直接触发 ReviewAgent（`a3a768b`）
- ✅ Session 持久化：sessionStorage + history reload（`65eda7f`, `3712204`）
- ❌ context-transport：仍然全量塞历史 / 硬截断（当前最大技术债）
- ❌ 第二/三个模型按场景分流：DeepSeek/GPT/Gemini provider 已建，缺路由逻辑
- ❌ verdict-detect：链路终止判定，靠 `recursion_limit=10` 兜底

**技术栈**（[MD §5](MY-AI-PLATFORM_1.md)）：
- 后端：Python + FastAPI + LangGraph
- ⚠️ **与设计文档不一致**：MD §5.1 原计划是 TypeScript + Fastify 纯函数（不用框架）。实际实现改用了 Python + FastAPI + LangGraph。原因是 LangGraph Python 生态比 JS 成熟，且 FastAPI 对 SSE 支持更开箱即用。如果你要按设计文档重构回 TS，这个 CL 会很大。
- 前端：Vue 3 + Vite + Tailwind
- 存储：SQLite（6 张表 — 见 [schema.py](my-ai-platform/packages/api/src/db/schema.py)）
- 通信：SSE（不是 WebSocket，Phase 1 只需服务端→客户端单向流）
- 包管理：pnpm workspace

**目录结构**：
```
my-ai-platform/
├── packages/
│   ├── api/          — FastAPI + LangGraph 后端
│   │   └── src/
│   │       ├── agent/        — 核心：registry / router / base
│   │       │   ├── agents/   — knowledge_agent / review_agent
│   │       │   ├── graphs/   — react_tool_loop / a2a_orchestration / daily_digest / capture_note / idea_collision
│   │       │   ├── providers/— deepseek / gpt / gemini
│   │       │   └── states/   — AgentState 类型定义
│   │       ├── context/      — assemble.py（三层记忆组装）
│   │       ├── db/           — schema.py（7 张表 + FTS5 + sqlite-vec）
│   │       ├── lib/          — llm_call.py / budget.py / embeddings.py
│   │       ├── tools/        — searchNotes / saveNote / synthesizeNotes / archiveNote / getNotesSummary
│   │       ├── routes/       — SSE + REST
│   │       ├── cli.py
│   │       └── main.py       — 应用入口
│   └── web/          — Vue 3 前端
├── prompts/          — knowledge.system.md / review.system.md
├── evals/            — golden.jsonl + run.py
├── docs/             — setup/ + retro/
├── playground/       — 学习材料（01-05 流式/ReAct 逐步理解）
└── scripts/          — seed-notes.py
```

**Phase 1 验收**（[retro](my-ai-platform/docs/retro/phase1-retro.md)，2026-06-09）：
1. ✅ 场景 A + D 端到端跑通，Vue 3 SSE 流式渲染正常
2. ✅ 黄金集 10/10（100%），JSON 解析失败率 0%
3. ✅ 2 跳 ReAct loop 日志可复现
4. ✅ phase1-retro.md 写完

## 核心架构概念

### 三条记忆层（[MD §4.4](MY-AI-PLATFORM_1.md)）
| 层 | 实现 | Clowder 对应 |
|----|------|-------------|
| 工作记忆 | SQLite messages 表，取最近 20 条 | `ContextAssembler.ts` |
| 情节记忆 | SQLite notes 表 + FTS5 | 自建 |
| 语义记忆 | sqlite-vec + sentence-transformers（已上线） | `context-transport.ts` |

### 安全边界（[MD §3.5](MY-AI-PLATFORM_1.md)）
- `MAX_A2A_DEPTH` = 5（实际实现值；Clowder 用 15，考虑成本暂取保守值）
- `MAX_A2A_MENTION_TARGETS` = 2（单条消息最多 @ 两个 Agent）
- `MAX_TOOL_LOOP_ITERATIONS` = 10（`recursion_limit`，LangGraph 兜底）
- `HISTORY_LIMIT` = 20（每个 session 最多取最近 N 条，硬截断，待 context-transport 替代）

### 笔记 status 字段（[MD §2 场景 C](MY-AI-PLATFORM_1.md)）
```python
# live → 当前有效，可被 AI 引用
# superseded → 被另一条笔记取代（需 superseded_by 指向新笔记）
# archived → 用户手动归档，不参与召回
```

## 关键约定

1. **诚实命名**：不要叫 prompt-chaining 为"Agent 自主路由"。见 [MD §3.0](MY-AI-PLATFORM_1.md)
2. **A2A 已上线但不是"Agent 自主路由"**：是 prompt 教模型写 `@agent` + 外部正则扫描，见 [router.py](my-ai-platform/packages/api/src/agent/router.py)
3. **Clowder 是参考，不是模板**：自建的价值是学 LLM 工程基线（成本/版本/evals/重试/观测），多 Agent 复杂度（context-transport / verdict-detect / multi-mention）只通过读 Clowder 源码学
4. **范围控制**：Phase 2 剩余项（context-transport / 按场景模型分流 / verdict-detect）优先于新功能
5. **promptVersion 一等公民**：从第一行代码就传下去（[MD §4.6](MY-AI-PLATFORM_1.md)）

## Phase 0 产物（1 周 Clowder 试用观察）✅

Phase 0 强制产出的三个文件（[MD §7.5](MY-AI-PLATFORM_1.md)），已完成：
- [观察日记](my-ai-platform/docs/setup/phase-0-journal.md) — 每天使用记录
- [不满足项清单](my-ai-platform/docs/setup/phase-0-gaps.md) — 如果结论是 (b)，这就是 Phase 1 锚点
- [结论简报](my-ai-platform/docs/setup/phase-0-verdict.md) — 一句话结论 + 3 条证据

## Phase 2 Retro

待写。当前进度：7/10 项完成。阻塞项：context-transport（最大技术债）。

## 下一步（优先级排序）

1. **context-transport** 🔴 — 给 `router.py:route_serial` 的 A2A 消息传递加上智能上下文裁剪，替代硬截断
2. **模型按场景分流** 🟡 — provider 已建（DeepSeek/GPT/Gemini），加一个 `resolve_model(agent_id, task)` 选择逻辑
3. **Phase 2 retro** 📋 — 写完 retro，验收当前阶段
4. **verdict-detect** 🟡 — 链路终止判定，防止 Agent 互踢皮球

## 已知技术债（原 Phase 1"故意不做"清单，[MD §3.6](MY-AI-PLATFORM_1.md)）

| 债项 | Clowder 对应 | 当前状态 | 丢了什么 |
|------|-------------|---------|---------|
| context-transport | `context-transport.ts` | 🔴 待做 | 跨 Agent 全量塞历史，token 膨胀；硬截断 20 条可能丢关键上下文 |
| verdict-detect | `verdict-detect.ts` | 🟡 靠 `recursion_limit=10` 兜底 | 两个 Agent 可能互踢皮球（A 说问 B，B 说问 A） |
| 模型按场景分流 | — | 🟡 provider 已建，缺路由 | 摘要/整理和深度推理用同一模型，成本不是最优 |
| MultiMentionOrchestrator | `MultiMentionOrchestrator.ts` | 🟡 串行取第一个 | 多 mention 只取前 2 个串行执行 |
| WorklistRegistry | `WorklistRegistry.ts` | ⬜ 未开始 | 进程崩了任务丢 |
| a2a-shadow-detection | `a2a-shadow-detection.ts` | 🟡 依赖正则 | 看不见行中间的 @mention，只扫行首 |
