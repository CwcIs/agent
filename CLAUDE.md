# 个人 Multi-Agent 知识工作台

> Claude 项目上下文文件。完整设计文档见 [MY-AI-PLATFORM_1.md](MY-AI-PLATFORM_1.md)（2298 行）。

## 项目本质

帮我把**碎片想法 → 结构化笔记**，让 AI 帮我连接、检索、挑战自己的思考。

两个核心机制（[MD §3.0](MY-AI-PLATFORM_1.md)）：
1. **ReAct Tool Loop**（单 Agent 内）— 模型自主决定调用工具
2. **Prompt-Chained Handoff**（跨 Agent）— 模型在输出写 `@gpt`，路由器字符串匹配后调度

**关键认知**：第二个不是"Agent 自主路由"，是 prompt 里教模型写 `@x` + 外部 30 行正则代码。

## 当前状态：Phase 1（4-6 周，进行中）

**Phase 1 范围**（[MD §8](MY-AI-PLATFORM_1.md)）：
- ✅ 单 Agent（Claude）
- ✅ ReAct tool loop（searchNotes / saveNote）
- ✅ 场景 A（碎片→结构化笔记）+ 场景 D（每日 AI 回顾）
- ✅ 硬编码流程（不上 YAML 工作流引擎）
- ✅ 工程基础：成本上限 / prompt 版本 / 统一重试 / .env 校验 / 黄金集 evals
- ❌ 不做：A2A handoff、第二/三个模型、向量检索、YAML 工作流

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
│   │       ├── agent/        — graphs/ + providers/ + states/
│   │       ├── context/      — assemble.py（三层记忆组装）
│   │       ├── db/           — schema.py（6 张表）
│   │       ├── lib/          — llm_call.py / budget.py
│   │       ├── tools/        — searchNotes / saveNote
│   │       ├── routes/       — SSE + REST
│   │       ├── cli.py
│   │       └── main.py       — 应用入口
│   └── web/          — Vue 3 前端
├── prompts/          — claude.system.md / gpt.system.md / gemini.system.md
├── evals/            — golden.jsonl + run.py
├── docs/             — setup/ + retro/
└── scripts/          — seed-notes.py
```

**Phase 1 验收标准**（[MD §8.8](MY-AI-PLATFORM_1.md)）：
1. 场景 A + D 连续用 7 天没崩
2. 黄金集通过率 ≥ 80%，JSON 解析失败率 < 5%
3. 至少一次完整 2 跳 ReAct loop 日志可复现
4. phase1-retro.md 写完

## 核心架构概念

### 三条记忆层（[MD §4.4](MY-AI-PLATFORM_1.md)）
| 层 | 实现 | Clowder 对应 |
|----|------|-------------|
| 工作记忆 | SQLite messages 表，取最近 20 条 | `ContextAssembler.ts` |
| 情节记忆 | SQLite notes 表 + FTS5 | 自建 |
| 语义记忆 | sqlite-vec（Phase 2 才上） | `context-transport.ts` |

### 安全边界（[MD §3.5](MY-AI-PLATFORM_1.md)）
- `MAX_A2A_DEPTH` = 15（Clowder 真实默认值，不是 5）
- `MAX_A2A_MENTION_TARGETS` = 2（单条消息最多 @ 两只猫）
- `MAX_TOOL_LOOP_ITERATIONS` = 建议 8–12，Phase 1 取 10

### 笔记 status 字段（[MD §2 场景 C](MY-AI-PLATFORM_1.md)）
```python
# live → 当前有效，可被 AI 引用
# superseded → 被另一条笔记取代（需 superseded_by 指向新笔记）
# archived → 用户手动归档，不参与召回
```

## 关键约定

1. **诚实命名**：不要叫 prompt-chaining 为"Agent 自主路由"。见 [MD §3.0](MY-AI-PLATFORM_1.md)
2. **Phase 1 不做 A2A**：先把 ReAct tool loop 跑通，再谈多 Agent 协作
3. **Clowder 是参考，不是模板**：自建的价值是学 LLM 工程基线（成本/版本/evals/重试/观测），多 Agent 复杂度（context-transport / verdict-detect / multi-mention）只通过读 Clowder 源码学
4. **范围控制**：Phase 1 不做清单贴在 [MD §8.7](MY-AI-PLATFORM_1.md)，每次想"顺手加 X"时回去看
5. **promptVersion 一等公民**：从第一行代码就传下去（[MD §4.6](MY-AI-PLATFORM_1.md)）

## Phase 0 产物（1 周 Clowder 试用观察）

Phase 0 强制产出的三个文件（[MD §7.5](MY-AI-PLATFORM_1.md)）：
- [观察日记](my-ai-platform/docs/setup/phase-0-journal.md) — 每天使用记录
- [不满足项清单](my-ai-platform/docs/setup/phase-0-gaps.md) — 如果结论是 (b)，这就是 Phase 1 锚点
- [结论简报](my-ai-platform/docs/setup/phase-0-verdict.md) — 一句话结论 + 3 条证据

## 我故意不做的复杂度（[MD §3.6](MY-AI-PLATFORM_1.md)）

这些 Clowder 有但 Phase 1 不做，知道丢了什么：
- `context-transport.ts`（跨 Agent 上下文裁剪）→ 我会全量塞历史，浪费 token
- `verdict-detect.ts`（链路终止判定）→ 两只猫可能互踢皮球
- `MultiMentionOrchestrator.ts`（多 mention 并行调度）→ 多 mention 只取第一个串行
- `WorklistRegistry.ts`（跨进程待办登记）→ 进程崩了任务丢
- `a2a-shadow-detection.ts`（行中间 @x telemetry）→ 看不见模型提到了别的猫
