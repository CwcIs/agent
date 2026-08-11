# 个人 Multi-Agent 知识工作台

> Codex 项目上下文文件。完整设计文档见 [MY-AI-PLATFORM_1.md](MY-AI-PLATFORM_1.md)（2298 行）。

## 项目本质

帮我把**碎片想法 → 结构化笔记**，让 AI 帮我连接、检索、挑战自己的思考。

两个核心机制（[MD §3.0](MY-AI-PLATFORM_1.md)）：
1. **ReAct Tool Loop**（单 Agent 内）— 模型自主决定调用工具
2. **Prompt-Chained Handoff**（跨 Agent）— 模型在输出写 `@gpt`，路由器字符串匹配后调度

**关键认知**：第二个不是"Agent 自主路由"，是 prompt 里教模型写 `@x` + 外部 30 行正则代码。

## 当前状态：Phase 1–3 ✅ → Phase 4 进行中（Router Graph 已切流）

**Phase 1**（2026-06-02 ~ 06-09）— [retro](my-ai-platform/docs/retro/phase1-retro.md) ✅ 全部验收通过

**Phase 2**（2026-06-09 ~ 06-14）— [retro](my-ai-platform/docs/retro/phase2-retro.md) ✅ 10/10 项完成

**Phase 3**（2026-06-16 ~ 06-22）— 已完成。已知技术债清零，Gemini BrainAgent 上线。
- ✅ 向量检索：sqlite-vec + sentence-transformers（`d94a0a2`）
- ✅ A2A 架构：Agent 注册表 + 路由循环 + `@agent` mention（`ad6df62`）
- ✅ ReviewAgent：prompt-chained thought challenger（`a4259bb`）
- ✅ 笔记编辑/删除/归档：DELETE + PATCH `/notes/:id`（`24253b8`）
- ✅ 跨笔记合成：`synthesize_notes` 工具（`0cdeb09`）
- ✅ `#hashtag` 显式路由：`#review` 直接触发 ReviewAgent（`a3a768b`）
- ✅ Session 持久化：sessionStorage + history reload（`65eda7f`, `3712204`）
- ✅ context-transport：智能上下文裁剪，替代硬截断（`43b6e37`）
- ✅ 模型按场景分流：`resolve_model(agent_id)` + GPT/Gemini provider（`829da89`）
- ✅ verdict-detect：链路终止判定 — natural_end / missing_handoff / loop_detected（本 commit）

**技术栈**（[MD §5](MY-AI-PLATFORM_1.md)）：
- 后端：Python + FastAPI + LangGraph
- ⚠️ **与设计文档不一致**：MD §5.1 原计划是 TypeScript + Fastify 纯函数（不用框架）。实际实现改用了 Python + FastAPI + LangGraph。原因是 LangGraph Python 生态比 JS 成熟，且 FastAPI 对 SSE 支持更开箱即用。如果你要按设计文档重构回 TS，这个 CL 会很大。
- 前端：Vue 3 + Vite + Tailwind
- 存储：SQLite（24 张实体表 + FTS5 + sqlite-vec — 见 [schema.py](my-ai-platform/packages/api/src/db/schema.py)）
- 通信：SSE（不是 WebSocket，Phase 1 只需服务端→客户端单向流）
- 包管理：pnpm workspace

**目录结构**：
```
my-ai-platform/
├── packages/
│   ├── api/          — FastAPI + LangGraph 后端
│   │   └── src/
│   │       ├── agent/        — 核心：Router Graph runtime / registry / governance / ReAct Agents
│   │       │   ├── agents/   — knowledge_agent / review_agent / brain_agent
│   │       │   ├── graphs/   — react_tool_loop / a2a_orchestration / daily_digest / capture_note / idea_collision
│   │       │   ├── providers/— deepseek / gpt / gemini
│   │       │   ├── router_graph_runtime.py — 生产外层确定性 Router Graph
│   │       │   ├── runtime_models.py — RouterState 与 Reducer
│   │       │   └── run_events.py — Run 事件账本与哈希链
│   │       ├── context/      — assemble.py（五层上下文）+ intent.py（显式任务意图）
│   │       ├── db/           — schema.py（24 张实体表 + FTS5 + sqlite-vec）
│   │       ├── lib/          — llm_call.py / budget.py / embeddings.py
│   │       ├── tools/        — search_notes / save_note / get_note / archive_note / getNotesSummary / synthesize_notes
│   │       ├── routes/       — SSE + REST
│   │       ├── cli.py
│   │       └── main.py       — 应用入口
│   └── web/          — Vue 3 前端
├── prompts/          — knowledge.system.md / review.system.md / gemini.system.md
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

### 当前生产运行时（2026-08-11）

- 外层：`router_graph_runtime.py` 管理输入、上下文、handoff governance、串并行、审批、checkpoint、verdict 和 Run Event。
- 内层：每个 Agent 保留 LangGraph ReAct Tool Loop，自主决定允许范围内的工具调用。
- `@mention` 仍只是候选 handoff；必须先转成 proposal 并通过 deterministic governance。
- 生产 `/chat/stream` 已切换到 Router Graph；旧 `route_serial()` 仅保留兼容，不是生产入口。
- Run 事实来源是 `agent_runs + run_events`；SSE 只负责传输，支持 `after_sequence` 补发。

### 数据库地图（24 张实体表）

| 领域 | 表 |
|------|----|
| 对话与知识 | `chat_threads`, `messages`, `notes`, `edges`, `pending_suggestions`, `idea_collisions`, `tag_aliases` |
| 检索与来源 | `embedding_meta`, `retrieval_events`, `note_stats`, `source_trace` |
| Agent 运行时 | `agent_runs`, `run_events`, `approval_requests`, `handoff_proposals`, `policy_decisions`, `execution_ledger`, `worklist` |
| 观测与评估 | `trace_events`, `llm_calls`, `llm_errors`, `eval_runs` |
| 产品扩展 | `daily_digests`, `custom_tools` |

> 上表按实际 schema 分组；`notes_fts` 和 sqlite-vec 虚拟表不计入 24 张实体表。

### 三条记忆层（[MD §4.4](MY-AI-PLATFORM_1.md)）
| 层 | 实现 | Clowder 对应 |
|----|------|-------------|
| 工作记忆 | SQLite messages 表，按优先级 + token 预算裁剪 | `ContextAssembler.ts` |
| 情节记忆 | SQLite notes 表 + FTS5 | 自建 |
| 语义记忆 | sqlite-vec + sentence-transformers（已上线） | `context-transport.ts` |

### 安全边界（[MD §3.5](MY-AI-PLATFORM_1.md)）
- `MAX_A2A_DEPTH` = 5（实际实现值；Clowder 用 15，考虑成本暂取保守值）
- `MAX_A2A_MENTION_TARGETS` = 2（单条消息最多 @ 两个 Agent）
- `MAX_TOOL_LOOP_ITERATIONS` = 10（`recursion_limit`，LangGraph 兜底）
- `HISTORY_LIMIT` = 20（保留兼容；context-transport 已用 token 预算替代条数限制）

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
4. **范围控制**：Phase 3 锚点 — A2A evals / MultiMentionOrchestrator / Gemini / a2a-shadow-detection
5. **promptVersion 一等公民**：从第一行代码就传下去（[MD §4.6](MY-AI-PLATFORM_1.md)）

## Phase 0 产物（1 周 Clowder 试用观察）✅

Phase 0 强制产出的三个文件（[MD §7.5](MY-AI-PLATFORM_1.md)），已完成：
- [观察日记](my-ai-platform/docs/setup/phase-0-journal.md) — 每天使用记录
- [不满足项清单](my-ai-platform/docs/setup/phase-0-gaps.md) — 如果结论是 (b)，这就是 Phase 1 锚点
- [结论简报](my-ai-platform/docs/setup/phase-0-verdict.md) — 一句话结论 + 3 条证据

## Phase 2 Retro

✅ 已写完 — 见 [retro](my-ai-platform/docs/retro/phase2-retro.md)。10/10 项全部完成。

## 下一步（Phase 3 后续 → Phase 4）✅

Phase 3 三个锚点全部完成 ✅：
- ✅ MultiMentionOrchestrator — 并行 fan-out（`orchestrator.py`）
- ✅ Gemini 接入 — BrainAgent 已注册，`@brain` 触发联想扩展
- ✅ WorklistRegistry — A2A 任务持久化 + crash recovery（`worklist.py`）

Phase 3 retro 已撰写 ✅ — 见 [retro](my-ai-platform/docs/retro/phase3-retro.md)

Phase 3 后续收尾（2026-06-22）✅：
- ✅ 前端多 Agent 并行渲染 UI — tool_start/tool_end 内联卡片 + Agent 切换分隔条 + 并行状态横幅
- ✅ 黄金集扩充 — golden_a2a.jsonl 从 10→17 条（brain 独立/多 mention 并行/边界案例/工具链）
- ✅ Phase 4 起步 — 每日回顾智能升级（趋势检测 + 异常发现 + 前端 badge 提示）

## Phase 4 后续方向

当前已上线：每日回顾趋势检测（`_detect_trends()` 纯数据计算，不调 LLM）。
下一步可选方向：
- RAG 外部网页/PDF 导入
- 用户画像/知识偏好
- 主动推送（daily digest 定时任务）
- 工具生态扩展（Web 搜索、日历集成等）

## 已知技术债（原 Phase 1"故意不做"清单，[MD §3.6](MY-AI-PLATFORM_1.md)）

| 债项 | Clowder 对应 | 当前状态 | 丢了什么 |
|------|-------------|---------|---------|
| context-transport | `context-transport.ts` | ✅ 已完成 | — |
| 模型按场景分流 | — | ✅ 已完成 | — |
| verdict-detect | `verdict-detect.ts` | ✅ 已完成 | — |
| a2a-shadow-detection | `a2a-shadow-detection.ts` | ✅ 已完成 | — |
| A2A evals 升级 | — | ✅ 已完成（golden_a2a.jsonl + run_a2a.py） | — |
| MultiMentionOrchestrator | `MultiMentionOrchestrator.ts` | ✅ 已完成（并行 fan-out） | — |
| WorklistRegistry | `WorklistRegistry.ts` | ✅ 已完成（crash recovery） | — |
