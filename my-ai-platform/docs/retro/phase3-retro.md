# Phase 3 Retro

**日期**：2026-06-16
**历时**：约 2 天（06-14 ~ 06-16）
**分支**：feature/week1

---

## 一句话结论

Phase 3 目标全部达成：已知技术债 7 项清零，MultiMentionOrchestrator 并行 fan-out 上线，Gemini BrainAgent 注册接入，WorklistRegistry crash recovery 就位，embedding 写入改为后台异步不阻塞 save_note。

---

## 3 条核心证据

1. **多 Agent 并行 fan-out 跑通**
   单条消息 `@review + @brain` 双 mention → `orchestrate_parallel()` 通过 `asyncio.create_task` 同时启动两个 Agent，interleaved SSE 事件按到达顺序输出。不是 mock——router.py 在 `len(mentions) > 1` 分支启用，单 mention 仍走串行。

2. **Gemini BrainAgent 端到端可触发**
   `@brain` mention → router 解析 → `BrainAgent` 实例 → `resolve_model("brain")` → `ChatGoogleGenerativeAI("gemini-2.0-flash")`。系统 prompt 教模型做联想扩展 + 跨域连接 + 跳跃距离标注。`@brain` 与 `@review` 可串行（A→B→C）也可并行（同时 fan-out）。

3. **WorklistRegistry 防丢任务**
   `router.py` 启动时读 worklist 表中 `pending/running` 项，重建 handoff 上下文重放。执行中通过 `mark_running/mark_done/mark_failed` 记录状态变更。进程崩了重启后自动恢复，不丢任务链。

---

## Phase 3 完成项（7/7）✅

| # | 项目 | 状态 | commit | 对应 Clowder |
|---|------|------|--------|-------------|
| 1 | verdict-detect（链路终止判定） | ✅ | `96486a8` | `verdict-detect.ts` |
| 2 | a2a-shadow-detection（行内 @mention） | ✅ | `e9da2c2` | `a2a-shadow-detection.ts` |
| 3 | A2A evals 升级（golden_a2a.jsonl + run_a2a.py） | ✅ | `e9da2c2` | — |
| 4 | MultiMentionOrchestrator（并行 fan-out） | ✅ | `8d501da` | `MultiMentionOrchestrator.ts` |
| 5 | WorklistRegistry（crash recovery） | ✅ | `e67e1c8` | `WorklistRegistry.ts` |
| 6 | Gemini BrainAgent（联想扩展 Agent） | ✅ | `95252b6` | — |
| 7 | Embedding 后台写入 + 快速关闭 | ✅ | `9fc2272` | — |

---

## 已知技术债清零

Phase 1 起标记的 7 项技术债全部解决：

| 债项 | Phase 1 状态 | Phase 2 状态 | Phase 3 状态 |
|------|:----------:|:----------:|:----------:|
| context-transport | ⬜ | ✅ | ✅ |
| 模型按场景分流 | ⬜ | ✅ | ✅ |
| verdict-detect | ⬜ | ⬜ | ✅ |
| a2a-shadow-detection | ⬜ | ⬜ | ✅ |
| A2A evals 升级 | ⬜ | ⬜ | ✅ |
| MultiMentionOrchestrator | ⬜ | 🟡 | ✅ |
| WorklistRegistry | ⬜ | ⬜ | ✅ |

---

## 做对的事

- **MultiMentionOrchestrator 用 asyncio.Queue 解耦**：各 Agent 在独立 task 中运行，事件推入共享队列，orchestrator 统一 interleave 输出。不用 barrier 等所有 Agent 完成——事件先到先出，前端可以逐步展示。
- **BrainAgent 设计克制**：只给 `search_notes` + `synthesize_notes` 两个只读工具，不注册 `save_note`。联想者不应越权写入——写入是 KnowledgeAgent 的职责。
- **embedding 后台化不改业务逻辑**：`save_note` 的返回值和状态码完全不变，`_background_embed` 内部 try/except 静默失败，embedding 失败不影响笔记已落库的事实。
- **atexit 而非侵入 shutdown hook**：用 `atexit.register(lambda: executor.shutdown(wait=False, cancel_futures=True))` 而不是在 FastAPI lifespan 中显式管理线程池生命周期。改动最小、不依赖框架。
- **WorklistRegistry 恢复逻辑在 router 入口**：`get_pending()` 在首次路由前执行，恢复失败的任务标记为 `failed` 并产出 error 事件。不阻塞新请求的处理。

---

## 踩过的坑

| 坑 | 根因 | 修法 |
|----|------|------|
| Ctrl+C 后进程卡 3-5 秒 | `ThreadPoolExecutor` 默认 `shutdown(wait=True)` 等 worker 线程跑完 `model.encode()` | `atexit` + `cancel_futures=True`，`9fc2272` |
| save_note 调用者感知 1-3s 延迟 | `await upsert_embedding()` 阻塞等待 CPU-bound encode | `asyncio.create_task` 转为 fire-and-forget，`9fc2272` |
| Gemini API key 未配置时 BrainAgent 静默失败 | `make_gemini()` raise RuntimeError，没有优雅降级 | `resolve_model()` 已有 fallback 机制——Gemini 不可用时降级到 DeepSeek，`providers/__init__.py` |

---

## Phase 3 后续（Phase 4 预研）

1. **前端多 Agent 并行渲染 UI** — 当前 ChatView 按 `agent_switch` 事件切换气泡，并行 fan-out 下 interleaved token 需要按 `agentId` 路由到独立气泡（而非追加到同一个 last message）
2. **黄金集扩充** — 当前 `golden_a2a.jsonl` 只有 knowledge→review 串行 5 条，需要补充：multi-mention 并行场景（@review+@brain）、brain 独立场景
3. **Phase 4 方向讨论** — 可能的方向：RAG 外挂网页/PDF、用户画像、主动推送（daily digest 升级）、工具生态扩展

---

## 技术栈现状（Phase 3 结束）

```
3 个 Agent:
  @knowledge  — DeepSeek (deepseek-chat)        工具: search/save/synthesize/summary
  @review     — GPT (gpt-4o-mini)               工具: search
  @brain      — Gemini (gemini-2.0-flash)       工具: search/synthesize

路由模式:
  - 无 mention    → knowledge 单 Agent ReAct loop
  - 单 mention    → A→B→C 串行 prompt-chain（最多 5 跳）
  - 多 mention    → 并行 fan-out（最多 2 目标）
  - #hashtag      → 显式路由跳过 knowledge

存储:
  - 8 张 SQLite 表 + FTS5 全文检索 + sqlite-vec 向量
  - messages 表按 token 预算裁剪（context-transport）
  - worklist 表持久化 A2A handoff（crash recovery）
```
