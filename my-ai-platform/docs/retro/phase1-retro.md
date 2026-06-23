# Phase 1 Retro

**日期**：2026-06-09  
**历时**：约 1 周  
**分支**：feature/week1

---

## 一句话结论

Phase 1 核心目标达成：ReAct tool loop 跑通，场景 A（碎片→笔记）和场景 D（每日回顾）端到端可用，evals 黄金集 10/10。

---

## 3 条核心证据

1. **ReAct 2跳 loop 可复现**  
   输入"帮我找找 Claude 相关的笔记"→ 模型自动调 `search_notes` → 拿到结果 → 组织语言返回。日志可见 `on_tool_start: search_notes` + `on_tool_end`，不是假的。

2. **evals 黄金集 10/10（100%）**  
   覆盖 5 类行为：概览调 `get_notes_summary`、关键词搜索调 `search_notes`、保存调 `save_note`、闲聊不调工具、知识问答不调工具。JSON 解析失败率 0%。

3. **前后端端到端跑通**  
   Vue 3 深色主题 UI + SSE 流式 token 渲染 + Markdown 表格正确显示。`/notes`、`/chat/stream`、`/digest` 三条路由全通，每日回顾追问按钮点击直接进入 chat。

---

## 做对的事

- **从第一行就传 promptVersion**：每次请求有版本号，改 prompt 后能对比行为变化
- **工具工厂模式**（`make_tools(conn)`）：db 连接从外部注入，测试和生产共用一套工具定义
- **evals 先于 retro**：有了黄金集才知道哪条 prompt 规则不够，而不是凭感觉改
- **惰性触发 + 缓存 `/digest`**：同一天多次打开不重复调 LLM，成本可控

---

## 踩过的坑

| 坑 | 根因 | 修法 |
|----|------|------|
| `call_model` 是同步函数 | 直接用了 `llm.invoke`，在 async 图里阻塞事件循环 | 改成 `async def` + `await llm.ainvoke` |
| `/chat/stream` 参数名错位 | 前端传 `?input=`，后端接 `?q=`，永远收到默认值 | 统一改成 `input` |
| Tailwind 样式全无 | 缺 `tailwind.config.js` + `postcss.config.js` + `style.css`，`main.ts` 没 import | 补齐三文件 + import |
| `/notes` 返回裸数组 | 前端期望 `{ notes: [...] }` | 改成包一层对象 |
| evals 首跑 80% | system prompt 没有区分"历史查询"和"知识问答" | 加规则 2（有没有记过 X → search）和规则 5（X 是什么 → 直接回答） |

---

## Phase 1 未做项（已知债务）

按 CLAUDE.md §"我故意不做的复杂度"：

- `context-transport`：每次请求全量塞历史，多轮后 token 会膨胀
- `verdict-detect`：没有链路终止判定，理论上可能死循环（靠 `recursion_limit=10` 兜底）
- 向量检索（sqlite-vec）：现在是 FTS5 关键词，语义相近但措辞不同的笔记找不到
- A2A handoff：只有单 Agent，多模型分工推到 Phase 2
- `daily_digest.py` 图：用了 routes 里内联实现，没有按设计文档建完整 LangGraph 图

---

## Phase 2 锚点（按优先级）

1. **向量检索**：接 sqlite-vec，`search_notes` 升级为语义检索
2. **context-transport**：超长对话裁剪，控制每次请求 token 数
3. **第二个模型**：摘要/整理用便宜模型，问答用强模型
4. **笔记编辑/删除**：目前只能新增，`superseded` 状态没有 UI 入口
