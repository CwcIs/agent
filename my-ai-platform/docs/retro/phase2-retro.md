# Phase 2 Retro

**日期**：2026-06-14
**历时**：约 1 周（06-09 ~ 06-14）
**分支**：feature/week1

---

## 一句话结论

Phase 2 核心目标达成：A2A 跨 Agent 接力跑通，context-transport 上线替换硬截断，模型按场景分流落地，verdict-detect 链路终止判定就位。10/10 项全部完成。

---

## 3 条核心证据

1. **A2A 端到端跑通**
   KnowledgeAgent 回答后写入 `@review <观点>` → router 正则解析 → 组装 context-transport 包 → ReviewAgent 接收并挑战。一次完整 `knowledge → review` 2 跳链路上过，不是 mock。

2. **context-transport 22/22 测试通过**
   `assemble_context()` 按 HIGH/MEDIUM/LOW 优先级裁剪历史，`package_handoff()` 组装四段式 A2A 交接包（用户意图 + 工具结果 + Agent A 结论 + review 观点）。Token 预算强制执行，被丢弃的消息生成一句话摘要。

3. **模型分流可验证**
   `resolve_model("review")` 在 `OPENAI_API_KEY` 存在时返回 `gpt-4o-mini`，不存在时 fallback `deepseek-chat`。`resolve_model("knowledge")` 始终走 DeepSeek。Fallback 有 WARNING 日志，不是静默降级。

---

## Phase 2 完成项（10/10）✅

| # | 项目 | 状态 | commit |
|---|------|------|--------|
| 1 | 向量检索（sqlite-vec + sentence-transformers） | ✅ | `d94a0a2` |
| 2 | A2A 架构（注册表 + 路由循环 + @mention） | ✅ | `ad6df62` |
| 3 | ReviewAgent（prompt-chained thought challenger） | ✅ | `a4259bb` |
| 4 | 笔记编辑/删除/归档（DELETE + PATCH） | ✅ | `24253b8` |
| 5 | 跨笔记合成（synthesize_notes 工具） | ✅ | `0cdeb09` |
| 6 | #hashtag 显式路由（#review → ReviewAgent） | ✅ | `a3a768b` |
| 7 | Session 持久化（sessionStorage + history reload） | ✅ | `65eda7f`, `3712204` |
| 8 | context-transport（智能上下文裁剪） | ✅ | `43b6e37` |
| 9 | 模型按场景分流（resolve_model + GPT/Gemini provider） | ✅ | `829da89` |
| 10 | verdict-detect（链路终止判定） | ✅ | 本 commit |

---

## 做对的事

- **context-transport 按优先级裁剪，不按条数**：用户消息 HIGH 永不被丢，长叙事 LOW 先被裁剪。这比 Phase 1 的 `LIMIT 20` 好得多——20 条短消息和 20 条长叙事完全不同的 token 消耗。
- **A2A 交接包结构化**：不是简单传 `@review 文本`，而是四段式（用户意图 + 工具事实 + Agent A 结论 + review 观点），Agent B 不会"失明"。
- **模型分流带 fallback**：`resolve_model()` 检测 API key 是否存在，不存在时 fallback 到 DeepSeek 并打 WARNING 日志。不会因为缺一个 key 整个链路崩掉。
- **GPT/Gemini provider 按需实现**：GPT 用于 ReviewAgent 的批判思维，Gemini 留 Phase 3。没有为了"看起来完整"三个一起上。

---

## 踩过的坑

| 坑 | 根因 | 修法 |
|----|------|------|
| router 串行只取第一个 mention | `parse_a2a_mentions` 的 for 循环 break 太早 | 改成收集到 list 后统一处理 |
| session 切换后历史丢失 | sessionStorage 没有持久化 session_id | 前端 `sessionStorage.setItem` + 后端 `_load_history` |
| A2A 深度无上限 | 没有 MAX_A2A_DEPTH 检查，两个 Agent 可能互踢 | 加 `depth < MAX_A2A_DEPTH` 循环条件 |
| context-transport 测试依赖 langgraph | 测试文件导入 `HumanMessage` / `AIMessage` 触发 langchain_core 全量加载 | 测试只依赖 `langchain_core.messages`，不碰 langgraph |

---

## Phase 2 遗留债务（Phase 3 处理）

| 债项 | Clowder 对应 | 丢了什么 | 优先级 |
|------|-------------|---------|--------|
| MultiMentionOrchestrator | `MultiMentionOrchestrator.ts` | 多 mention 串行取第一个，不是并行 | 🟡 |
| WorklistRegistry | `WorklistRegistry.ts` | 进程崩了任务丢 | ⬜ |
| a2a-shadow-detection | `a2a-shadow-detection.ts` | 依赖正则，看不见行中间的 @mention | 🟡 |

---

## Phase 3 锚点（按优先级）

1. **evals 升级** — Phase 1 黄金集只测单 Agent tool call，Phase 3 需要 A2A 端到端 evals（knowledge → review 链路至少 5 条）
2. **MultiMentionOrchestrator** — 支持一个用户消息同时 @多个 Agent 并行执行
3. **Gemini 接入** — 联想/头脑风暴场景，前提是黄金集人评出现 ≥5 条"需要联想视角"的样本
4. **a2a-shadow-detection** — 用 AST/更多正则覆盖行内 @mention
