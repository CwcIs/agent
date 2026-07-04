# Phase 4–8 架构计划书

> **日期**：2026-07-04
> **状态**：Phase 3 ✅ 完成，Phase 4 部分起步
> **分支**：feature/week1

---

## 目录

1. [当前状态回顾](#1-当前状态回顾)
2. [总体路线图](#2-总体路线图)
3. [Phase 4：知识生态深化](#3-phase-4知识生态深化)
4. [Phase 5：外部知识接入](#4-phase-5外部知识接入)
5. [Phase 6：主动智能](#5-phase-6主动智能)
6. [Phase 7：工具生态扩展](#6-phase-7工具生态扩展)
7. [Phase 8：平台化与打磨](#7-phase-8平台化与打磨)
8. [技术决策记录](#8-技术决策记录)
9. [风险与依赖](#9-风险与依赖)

---

## 1. 当前状态回顾

### 1.1 Phase 3 结束时架构全貌

```
─────────────────────────────────────────────────────────
                    3 个 Agent
─────────────────────────────────────────────────────────
  @knowledge  → DeepSeek (deepseek-chat)
                 工具: search/save/get/archive/summary/synthesize/relations
  @review     → GPT (gpt-4o-mini)
                 工具: search
  @brain      → Gemini (gemini-2.0-flash)
                 工具: search/get/synthesize
─────────────────────────────────────────────────────────
                    路由模式
─────────────────────────────────────────────────────────
  无 mention   → knowledge 单 Agent ReAct loop
  单 mention   → A→B→C 串行 prompt-chain（最多 5 跳）
  多 mention   → 并行 fan-out（最多 2 目标）
  #hashtag     → 显式路由跳过 knowledge
─────────────────────────────────────────────────────────
                    存储层（9 表）
─────────────────────────────────────────────────────────
  notes / notes_fts     — 笔记 + 全文检索
  messages              — 对话历史
  daily_digests         — 每日回顾（含 trends/anomalies）
  llm_calls / llm_errors— 审计追踪（含 trace_id/agent_id）
  eval_runs             — 黄金集运行记录
  embedding_meta        — 向量模型指纹
  edges                 — 笔记关系图谱
  worklist              — A2A 任务持久化 + crash recovery
─────────────────────────────────────────────────────────
                    三条记忆层
─────────────────────────────────────────────────────────
  工作记忆 → messages 表 + CC 五层金字塔裁剪
              (L1 offload → burst detect → anchor → tombstone)
  情节记忆 → notes + FTS5 + edges 关系图谱
  语义记忆 → sqlite-vec + sentence-transformers
─────────────────────────────────────────────────────────
                    上下文注入
─────────────────────────────────────────────────────────
  assemble_context() 已注入相关笔记（FTS5 关键词匹配）
  用户输入 → 搜索笔记库 → 格式化为上下文段 → 插入历史开头
─────────────────────────────────────────────────────────
                    前端
─────────────────────────────────────────────────────────
  Vue 3 + Vite + Tailwind
  4 个视图: ChatView / NoteListView / DailyDigestPanel / App
  多 Agent 并行渲染: tool_start/tool_end 内联卡片
                      + Agent 切换分隔条 + 并行状态横幅
─────────────────────────────────────────────────────────
```

### 1.2 Phase 4 已起步内容

| 功能 | 状态 | 位置 |
|------|------|------|
| 每日回顾趋势检测 | ✅ 已上线 | `daily_digest.py` — `_detect_trends()` |
| 每日回顾异常发现 | ✅ 已上线 | `daily_digest.py` — 前端 badge 提示 |
| 相关笔记上下文注入 | ✅ 已上线 | `assemble.py` — `_fetch_related_notes()` |
| 笔记关系图谱 edges 表 | ✅ 已建表 | `schema.py` — 5 种关系类型 |
| `get_note_relations` 工具 | ✅ 已上线 | `tools/__init__.py` |
| `[[wikilink]]` 自动解析 | ✅ 已上线 | `save_note` 触发 `_create_wikilink_edges()` |

---

## 2. 总体路线图

```
Phase 4           Phase 5           Phase 6           Phase 7           Phase 8
知识生态深化      外部知识接入       主动智能           工具生态扩展       平台化与打磨
─────┬─────      ─────┬─────       ─────┬─────       ─────┬─────       ─────┬─────
     │               │                  │                  │                  │
 4.1 关系图谱      5.1 Web 导入      6.1 定时推送       7.1 Web 搜索      8.1 性能优化
 4.2 知识可视化    5.2 文件导入      6.2 知识缺口       7.2 日历集成      8.2 可观测面板
 4.3 Idea Collision 5.3 来源追踪    6.3 复习提醒       7.3 自定义工具     8.3 笔记导出
 4.4 标签智能      5.4 引用链        6.4 写作提示       7.4 多模态笔记     8.4 插件系统
 4.5 Daily Digest  5.5 外部搜索集成  6.5 用户画像       7.5 代码执行       8.5 安全加固
     2.0                                                                   8.6 文档
     │               │                  │                  │                  │
─────┴─────      ─────┴─────       ─────┴─────       ─────┴─────       ─────┴─────
  2-3 周           2-3 周            2-3 周            3-4 周            2-3 周
```

**总预估**：12–16 周（约 3–4 个月），按个人业余项目节奏。

### 设计原则

1. **每一 Phase 可独立上线**：不做"Phase 5 依赖 Phase 4 全部完成"的设计。每个子模块独立可交付。
2. **数据先行，UI 跟进**：先在 schema + tool 层面落地，再配前端界面。
3. **成本意识**：LLM 调用按场景分级——高频操作用 cheap model，深度分析用 capable model。
4. **渐进式复杂度**：默认简单方案（规则/统计），只在数据证明需要时才上 LLM。
5. **不破坏现有 evals**：每个 Phase 结束时 golden 集通过率不得低于当前基线。

---

## 3. Phase 4：知识生态深化

> **目标**：让笔记之间的关系从"被动记录"变成"主动发现"，让知识图谱从静态存储变成动态生长。
> **锚点**：关系图谱自动发现 + 可视化 + Idea Collision 升级 + 标签智能 + Daily Digest 2.0

### 4.1 关系图谱自动发现（4.1）

#### 现状
- `edges` 表已建，5 种关系类型：`wikilink` / `evolved_from` / `supersedes` / `contradicts` / `related`
- `[[wikilink]]` 自动解析已上线（`save_note` 时触发）
- `get_note_relations` 工具已上线

#### 目标
从手动 `[[wikilink]]` → 自动发现三种新关系：

| 关系 | 触发方式 | 实现 |
|------|---------|------|
| `similar` | 语义相似度 > 阈值 | sqlite-vec 余弦相似度，save_note 时后台计算 |
| `contradicts` | 两篇笔记对同一话题持相反观点 | LLM 批处理（每日 digest 时顺带检测） |
| `evolved_from` | 新笔记显式覆盖/更新旧笔记 | 用户在 save 时传 `supersedes_id` 参数 |

#### 实现计划

```
后端改动:
  save_note 工具:
    + supersedes_id 可选参数 → 自动创建 evolved_from edge

  _background_embed 升级:
    + 向量写入后 → 计算与新笔记最相似的 top 5 已有笔记
    + 相似度 > 0.75 → 自动创建 similar edge
    + 相似度 0.5-0.75 → 存入 pending_suggestions 表，等用户确认

  daily_digest.py 升级:
    + _detect_contradictions() — 批量扫描最近 N 天笔记对
      找语义相似但结论相反的笔记 → 创建 contradicts edge（低置信度）
    + 在每日回顾 narrative 中提及新发现的关系

  schema 新增:
    pending_suggestions 表:
      id / from_id / to_id / relation / confidence / status / created_at
      status ∈ {pending, accepted, rejected}

新增工具:
  suggest_relation(from_id, to_id, relation) — LLM 判断是否应建立关系
  accept_suggestion(suggestion_id) / reject_suggestion(suggestion_id)

前端改动:
  笔记详情面板增加"关系"tab
  展示 outgoing / incoming edges，按关系类型分组
```

#### 验收标准
- [ ] `similar` edge 自动创建可复现（save_note → 查 edges 表有记录）
- [ ] `contradicts` 在 daily digest 中至少出现 1 次（需 ≥2 篇语义相似但观点不同的笔记）
- [ ] `evolved_from` 通过 `supersedes_id` 参数创建
- [ ] pending_suggestions 表写入 + accept/reject 流程跑通

### 4.2 知识图谱可视化（4.2）

#### 目标
前端新增一个 **GraphView**，以力导向图展示笔记关系网络。

#### 实现计划

```
前端新页面: src/views/GraphView.vue

技术选型: D3.js force simulation（轻量，不引入重型图数据库）

功能:
  1. 节点 = 笔记（大小 = 连接数，颜色 = 标签分组）
  2. 边 = 关系（颜色区分 wikilink/similar/evolved_from/contradicts）
  3. 点击节点 → 侧边栏展示笔记摘要 + 关系列表
  4. 双击节点 → 跳转到笔记详情 / 对话中展开
  5. 搜索框 → 高亮匹配笔记及其 N 跳邻居
  6. 时间滑块 → 只看某时间段的笔记

后端新增 API:
  GET /notes/graph?center_id=xxx&depth=2
    → 返回 { nodes: [...], edges: [...] }
    以 center_id 为中心做 BFS，depth 控制跳数

  GET /notes/graph/full
    → 返回全图（笔记数 < 200 时可用，超过则截断 + 提示）
```

#### 验收标准
- [ ] GraphView 可访问，节点和边渲染正常
- [ ] 点击节点展示笔记摘要
- [ ] 搜索高亮 + N 跳邻居展开
- [ ] 100 条笔记以下全图加载 < 2s

### 4.3 Idea Collision 升级（4.3）

#### 现状
`idea_collision.py` 有骨架但基本是占位符——只有一个简单的 LangGraph StateGraph 定义，没有实际碰撞逻辑。

#### 目标
让系统主动提出"你记过 A 和 B，它们底层在说同一件事"的洞察——这是整个平台最高价值的 AI 能力之一。

#### 实现计划

```
碰撞触发时机:
  1. save_note 时：新笔记 vs 已有笔记库，找意外关联
  2. daily digest 时：批量扫描最近 7 天笔记对
  3. 用户手动触发："帮我发现意外关联"

碰撞算法:
  Phase A — 候选对生成（便宜，不用 LLM）:
    1. 向量相似度 top 20（语义相近）
    2. 标签重合度 ≥1（同一主题域）
    3. 时间相近 + 标签不同（同一天记的不同话题）

  Phase B — LLM 碰撞评分（贵，只对候选对调用）:
    prompt: "以下是两篇笔记，它们是否有意外关联？
            - 表面无关但底层相似的模式
            - 互相矛盾的观点
            - 可以组合出新想法
            返回 {score: 1-10, connection: '一句话描述', angle: 'pattern|contradiction|synthesis'}"

  Phase C — 入库 + 通知:
    碰撞 score ≥ 7 → 存入 idea_collisions 表
    前端 DailyDigestPanel 展示"本周意外发现"

schema 新增:
  idea_collisions 表:
    id / note_a_id / note_b_id / score / connection / angle
    / is_read / created_at

新增工具:
  detect_collisions(topic: str) — 围绕 topic 找意外关联
  注册给 KnowledgeAgent + BrainAgent

前端改动:
  DailyDigestPanel 增加"意外发现"section
  ChatView 中 Agent 可主动提及碰撞结果
```

#### 验收标准
- [ ] save_note 触发碰撞检测（后台异步）
- [ ] score ≥ 7 的碰撞存入 idea_collisions 表
- [ ] DailyDigestPanel 展示本周碰撞发现
- [ ] 手动"帮我发现意外关联"调用 detect_collisions 返回结果

### 4.4 标签智能（4.4）

#### 目标
从手动输入 tags → AI 辅助标签建议 + 标签自动归类。

#### 实现计划

```
自动标签建议:
  save_note 时:
    如果用户未传 tags → LLM 读 title+content，建议 2-4 个标签
    用 cheap model（DeepSeek），latency < 1s
    前端展示建议标签，用户可点击确认/修改/忽略

标签归一化:
  定时任务（daily digest 时顺带做）:
    扫描 tags_json 列 → 发现同义标签（如 "AI" vs "人工智能" vs "ai"）
    → 合并建议存入 pending_suggestions 表

标签层级:
  允许用户定义标签层级（如 技术 > AI > LLM）
  前端标签导航按树形展示

schema 改动:
  tag_aliases 表:
    id / canonical / alias / created_at
    （"AI" 是 canonical，"人工智能"和"ai"是 alias）

新增工具:
  suggest_tags(title, content) → 返回建议标签列表
  merge_tags(canonical, aliases[]) → 合并同义标签

前端改动:
  save_note 时展示建议标签 chips
  标签管理页面（批量合并/重命名）
  NoteListView 侧边栏标签树
```

#### 验收标准
- [ ] 不传 tags 时 AI 建议标签可展示
- [ ] 标签归一化检测到 ≥1 组同义标签
- [ ] 标签树导航可用

### 4.5 Daily Digest 2.0（4.5）

#### 现状
- 基础版已上线：fetch → generate → cache
- `_detect_trends()` 纯数据计算（不调 LLM）：统计每日笔记数/标签分布/活跃度
- `trends` / `anomalies` 列已加入 daily_digests 表

#### 目标
从"纯数据统计"升级到"LLM 驱动的洞察综述"。

#### 实现计划

```
升级点:

1. LLM 趋势分析（替换纯数据计算）:
   _detect_trends() → _analyze_trends_llm()
   输入：最近 7 天笔记的 title + summary + tags
   prompt: "分析用户本周的思考轨迹。发现：
           1. 话题迁移模式（从 A → B → C 的知识演进）
           2. 反复出现的主题（本周至少出现 2 次）
           3. 与上周的对比变化
           4. 值得深入探索的方向（1-2 个）"
   输出：结构化 JSON → 写入 trends 列

2. 周回顾 + 月回顾:
   新增 /digest/weekly 和 /digest/monthly
   复用 daily digest 的 graph 结构，扩大时间窗口
   周回顾：每周日自动生成
   月回顾：每月 1 号自动生成

3. 前端升级:
   DailyDigestPanel 改为三 tab：日 / 周 / 月
   趋势图：笔记数折线图（7 天）+ 话题标签云
   "本周意外发现" section（来自 idea_collisions）

4. 前端 badge 提示升级:
   当前只有简单 badge → 改为智能提醒：
   "你有 3 条笔记超过 30 天没回顾"
   "本周发现 2 个可能的矛盾观点"
   "话题 X 已经一周没更新了"
```

#### 验收标准
- [ ] LLM 趋势分析输出结构正确的 JSON（narrative + migrations + recurring + explore）
- [ ] 周回顾 / 月回顾 API 返回正常
- [ ] 前端三 tab 切换可用
- [ ] 智能提醒 badge 至少展示 2 种类型

---

## 4. Phase 4 交付清单

| # | 功能 | 优先级 | 预估 |
|---|------|--------|------|
| 4.1 | 关系图谱自动发现 | 🟡 | 3-4 天 |
| 4.2 | 知识图谱可视化 | 🟡 | 3-4 天 |
| 4.3 | Idea Collision 升级 | 🔴 | 4-5 天 |
| 4.4 | 标签智能 | 🟢 | 2-3 天 |
| 4.5 | Daily Digest 2.0 | 🔴 | 3-4 天 |

**Phase 4 总计**：约 2–3 周

---

## 5. Phase 5：外部知识接入

> **目标**：打破"只记自己想法"的边界，让外部网页/文档/PDF 变成可检索、可关联的知识资产。
> **锚点**：Web 抓取 → 笔记转换 → 来源追踪 → 引用链

### 5.1 Web 页面导入（5.1）

#### 实现计划

```
新增工具:
  import_webpage(url: str, tags?: str) → 抓取网页 → 存为笔记

实现:
  1. 服务端 HTTP GET → BeautifulSoup 提取正文（去广告/导航/侧栏）
  2. readability-lxml 算法提取主内容
  3. title → notes.title，正文 → notes.content
  4. source = url，tags 由用户指定或 AI 建议
  5. 后台异步 embedding
  6. 返回 note_id，前端展示"已导入"卡片

技术选型:
  - trafilatura（Python，比 readability 更准，专门做 web 正文提取）
  - 或者 readability-lxml + BeautifulSoup 组合
  - 推荐 trafilatura：pip install trafilatura，纯 Python，维护活跃

安全:
  - URL 白名单/黑名单（防止 SSRF 打内网）
  - 请求超时 15s
  - 内容大小上限 5MB
  - 只抓 text/html，拒绝 binary

新增 API:
  POST /notes/import/web
    body: { url, tags?, auto_tags?: bool }
    → 返回 { note_id, title, word_count, source_url }
```

### 5.2 文件导入（5.2）

#### 实现计划

```
支持格式:
  - Markdown (.md) — 直接解析 frontmatter + content
  - PDF (.pdf)    — PyMuPDF / pdfplumber 提取文本
  - 纯文本 (.txt) — 直接读取

新增 API:
  POST /notes/import/file
    multipart/form-data: file + tags?
    → 返回 { note_id, title, word_count, source_file }

新增工具:
  import_file(file_path: str, tags?: str) — 给 Agent 用的文件导入工具
  注册给 KnowledgeAgent

前端:
  笔记列表页增加"导入"按钮 → 弹出对话框
  支持拖拽文件 + 粘贴 URL
  导入进度条（大文件解析需要时间）
```

### 5.3 来源追踪（5.3）

#### 目标
每篇笔记记录"从哪来的"——是自己想的还是从外部导入的。

#### 实现计划

```
schema 改动:
  notes 表新增列:
    source_url  TEXT    — 原始 URL（网页导入）
    source_file TEXT    — 原始文件名（文件导入）
    source_type TEXT    — 'user' | 'web' | 'file' | 'agent_generated'
    word_count  INTEGER — 正文字数

  source 列已存在但未充分利用 → 升级为结构化来源追踪

新增:
  source_trace 表:
    id / note_id / source_type / source_url / source_file
    / imported_at / content_hash / fetch_status
    fetch_status ∈ {ok, partial, failed}

功能:
  - 查看笔记时展示"来源"行（可点击跳转原始网页）
  - 来源失效检测（定时检查 URL 是否仍可访问）
  - "从同一来源导入的所有笔记"聚合视图
```

### 5.4 引用链（5.4）

#### 目标
追踪知识演化路径：原始网页 → 笔记 A → 笔记 B（发展了 A 的观点）→ 笔记 C（推翻了 B）。

#### 实现计划

```
edges 表已支持: evolved_from / supersedes / contradicts

升级点:
  1. 可视化引用链：选中一篇笔记 → 展示完整的"来源树"和"衍生树"
  2. "知识溯源"工具：给定一篇笔记，沿着 evolved_from 链回溯到最早的原始来源
  3. 影响度评估：某篇笔记被多少后续笔记引用 → 在 GraphView 中节点大小体现

新增 API:
  GET /notes/:id/trace
    → 返回 { ancestors: [...], descendants: [...] }
    ancestors: 沿着 evolved_from + wikilink 回溯
    descendants: 沿着 edges 正向追溯
```

### 5.5 外部搜索集成（5.5）

#### 目标
用户聊天时，Agent 可以主动说"这个问题笔记库里没有，要我帮你搜一下吗？"

#### 实现计划

```
新增工具:
  web_search(query: str, k: int = 3) → 搜索 web 返回结果摘要
  注册给 KnowledgeAgent

实现选项:
  A. SerpAPI / Brave Search API（付费，质量高）
  B. DuckDuckGo 免费 API（免费，质量中等）
  C. 自建（爬虫，维护成本高）

Phase 5 推荐: 选项 B（DuckDuckGo），零成本，够用
后续可升级到 A

Agent prompt 升级:
  "如果笔记库搜不到相关内容，告知用户，并询问是否需要 web_search"

安全:
  - 搜索结果只展示标题+摘要，不自动抓取
  - 用户确认后才 import_webpage
```

---

## 5. Phase 5 交付清单

| # | 功能 | 优先级 | 预估 |
|---|------|--------|------|
| 5.1 | Web 页面导入 | 🔴 | 2-3 天 |
| 5.2 | 文件导入 | 🟡 | 2-3 天 |
| 5.3 | 来源追踪 | 🟡 | 2 天 |
| 5.4 | 引用链 | 🟢 | 2 天 |
| 5.5 | 外部搜索集成 | 🟢 | 1-2 天 |

**Phase 5 总计**：约 2–3 周

---

## 6. Phase 6：主动智能

> **目标**：系统从"被动响应"变成"主动服务"——不等你问，它先提醒你。
> **锚点**：定时推送 + 知识缺口 + 复习提醒 + 写作提示 + 用户画像

### 6.1 定时推送（6.1）

#### 目标
每天早上 8 点（或用户指定时间），系统自动生成 Daily Digest 并推送通知。

#### 实现计划

```
方案 A — 外部 cron（推荐）:
  - 操作系统 cron / systemd timer 触发 API 调用
  - 简单可靠，不增加 Python 进程复杂度
  - Windows 用 Task Scheduler，macOS/Linux 用 cron

方案 B — 内置调度器:
  - FastAPI 内 APScheduler
  - 好处：不依赖 OS，配置集中在 app 内
  - 坏处：进程崩了调度也停

推荐方案 A，运行:
  # macOS/Linux crontab:
  0 8 * * * curl -X POST http://localhost:8000/digest/daily/generate

  # Windows Task Scheduler:
  每天 8:00 触发 powershell Invoke-WebRequest

推送渠道（按优先级）:
  1. 前端 badge（已有）
  2. 系统通知（Web Notification API）
  3. 邮件（可选，需要 SMTP 配置）
  4. 微信/Telegram bot（远期可选）

前端升级:
  - 请求 Web Notification 权限
  - 新 digest 生成后推送浏览器通知
  - Service Worker 支持后台推送（PWA 化）
```

### 6.2 知识缺口检测（6.2）

#### 目标
AI 主动发现"你应该了解但还没记过的领域"。

#### 实现计划

```
算法:
  1. 对已有笔记做话题聚类（向量聚类或标签分组）
  2. 在每个话题簇内找"缺失的维度"
     例：记了 5 篇"AI 产品设计"，但 0 篇"AI 产品定价"
  3. 对每个缺口生成一句话建议
  4. 在 Daily Digest 中展示"本周建议探索的方向"

实现:
  daily_digest.py — _detect_gaps()
  输入：最近 30 天笔记的 title + tags + summary
  LLM prompt: "用户的知识库有以下话题覆盖。找出 1-2 个值得探索但尚未涉及的方向。
               每个缺口说明为什么重要，以及可以从哪里开始。"

新增工具:
  suggest_gaps(topic?: str) → 返回缺口建议列表
  注册给 KnowledgeAgent
```

### 6.3 复习提醒（6.3）

#### 目标
间隔重复式的知识复习——不让已记录的思考被遗忘。

#### 实现计划

```
算法（简化版 SM-2）:
  每篇笔记记录:
    last_reviewed_at  — 最后复习时间
    review_interval   — 当前复习间隔（天）
    review_count      — 已复习次数

  复习间隔递进:
    review_count 0 → interval 1 天
    review_count 1 → interval 3 天
    review_count 2 → interval 7 天
    review_count 3 → interval 14 天
    review_count 4 → interval 30 天
    ...

  到期检测（daily digest 时）:
    SELECT * FROM notes WHERE last_reviewed_at + review_interval < now()
    → 生成"今日待复习"列表

schema 改动:
  notes 表新增列:
    last_reviewed_at TEXT
    review_interval  INTEGER DEFAULT 1
    review_count     INTEGER DEFAULT 0

新增工具:
  review_note(note_id) → 展示笔记内容 + 记录复习时间
  get_due_reviews() → 返回到期待复习的笔记列表

前端:
  DailyDigestPanel 增加"待复习"section
  ChatView 中 Agent 可提醒"你有 N 条笔记该复习了"
```

### 6.4 写作提示（6.4）

#### 目标
基于用户的知识积累，AI 主动建议"这个话题你已经积累够了，要不要写一篇总结？"

#### 实现计划

```
触发条件:
  同一标签下笔记数 ≥ 5 篇 → 触发写作提示
  同一话题的笔记时间跨度 > 30 天 → "你的思考在演化，值得回顾"

实现:
  daily_digest.py — _suggest_writing()
  输入：话题簇（标签+向量聚类）
  输出：1-2 个写作建议 + 可引用的笔记列表

展示:
  DailyDigestPanel "写作灵感" section
  Agent 主动提及："你在 X 话题上已经记了 7 条笔记，要我帮你综合成一篇长文吗？"
```

### 6.5 用户画像（6.5）

#### 目标
让系统了解用户的知识偏好、关注领域、思考风格，从而提供更个性化的服务。

#### 实现计划

```
画像维度:
  1. 兴趣分布 — 从 tags + 向量聚类提取 top 5 话题
  2. 活跃时段 — 从 messages.created_at 分析用户活跃时间
  3. 思考风格 — 笔记是偏"分析/批判"还是"发散/联想"
                 （用 LLM 对笔记样本做分类）
  4. 知识盲区 — 用户可能回避或未涉及的话题
  5. 常用 Agent — 哪些 Agent 被调用最频繁

存储:
  不建新表，利用现有数据计算，结果缓存在内存
  画像数据敏感度高 → 只存本地，不上传

使用场景:
  - Daily Digest 根据用户活跃时段推送
  - BrainAgent 根据兴趣分布做更精准的联想
  - KnowledgeAgent 对新笔记做"是否符合你的思考风格"的反馈

实现:
  新建 user_profile.py — gather() 函数，聚合各表数据
  GET /user/profile → 返回画像 JSON（前端可展示"我的知识画像"页面）
```

---

## 6. Phase 6 交付清单

| # | 功能 | 优先级 | 预估 |
|---|------|--------|------|
| 6.1 | 定时推送 | 🟡 | 2 天 |
| 6.2 | 知识缺口检测 | 🟡 | 2 天 |
| 6.3 | 复习提醒 | 🔴 | 2-3 天 |
| 6.4 | 写作提示 | 🟢 | 1-2 天 |
| 6.5 | 用户画像 | 🟡 | 2-3 天 |

**Phase 6 总计**：约 2–3 周

---

## 7. Phase 7：工具生态扩展

> **目标**：让 Agent 不止能搜笔记，还能搜 Web、查日历、跑代码——变成一个真正的"AI 助手"。
> **锚点**：Web 搜索 + 日历 + 自定义工具 + 多模态 + 代码执行

### 7.1 Web 搜索工具（7.1）

#### 目标
Agent 能实时搜索互联网获取最新信息。

#### 实现计划

```
Phase 5 已做基础版（DuckDuckGo 免费搜索）。
Phase 7 升级到生产级:

搜索提供商:
  1. Brave Search API（推荐）— 免费 tier 2000 query/月，质量好
  2. SerpAPI — 付费，覆盖 Google/Bing 等
  3. Tavily — 专为 AI Agent 设计，自带内容提取

推荐 Tavily：
  - 专为 LLM Agent 设计
  - 返回结构化结果（title/url/content/score）
  - 自动提取正文内容
  - 免费 tier 1000 query/月

工具:
  web_search(query, k=5, include_content=True)
    → 返回 [{title, url, snippet, content?, score}]
  web_fetch(url) → 抓取单页正文（复用 5.1 的 import_webpage 逻辑，但不存笔记）

Agent prompt 改动:
  "当笔记库和你的知识都不足以回答时，使用 web_search 查找最新信息。
   引用外部信息时标注来源 URL。"
```

### 7.2 日历集成（7.2）

#### 目标
Agent 能读写用户的日历，把笔记和日程关联起来。

#### 实现计划

```
方案: CalDAV 协议（支持 Google Calendar / Apple Calendar / Nextcloud）

Python 库: caldav（纯 Python CalDAV 客户端）

功能:
  1. 读取今日/本周日程 → 注入为 Daily Digest 上下文
  2. 从笔记创建日程 → "记下来下周要做的事" → Agent 帮你加到日历
  3. 会议笔记关联 → 把会议时间和笔记内容关联

工具:
  get_today_events() → 返回今日日程列表
  get_week_events() → 返回本周日程
  create_event(title, date, time?, duration_min?, notes?)
    → 创建日历事件

安全:
  - CalDAV 密码存环境变量，不写 DB
  - 只读日历可配置（默认只读，写操作需用户确认）
```

### 7.3 自定义工具构建器（7.3）

#### 目标
用户可以在前端界面定义自己的 API 工具，Agent 就能调用。

#### 实现计划

```
工具定义格式:
  {
    name: "weather_query",
    description: "查询指定城市的天气",
    endpoint: "https://api.openweathermap.org/data/2.5/weather",
    method: "GET",
    params: { q: "$city", appid: "$API_KEY" },
    headers: {},
    output_template: "{{city}}天气：{{temp}}°C，{{description}}"
  }

存储:
  custom_tools 表:
    id / name / description / endpoint / method
    / params_json / headers_json / output_template
    / enabled / created_at

工具执行:
  make_tools() 加载 custom_tools 表 → 动态生成 LangChain Tool
  参数中的 $VAR 从环境变量替换
  调用时用 httpx 发请求 → 按 output_template 格式化返回

前端:
  工具管理页面：新增 / 编辑 / 启用 / 禁用 / 测试
  工具模板市场（预设常用 API：天气、新闻、汇率等）
```

### 7.4 多模态笔记（7.4）

#### 目标
笔记可以包含图片、音频（语音笔记）。

#### 实现计划

```
Phase 7 范围:
  图片笔记 — 用户上传图片 + 文字说明
  AI 自动用多模态模型理解图片内容（如 GPT-4o / Gemini）

存储:
  图片文件存本地文件系统（data/attachments/）
  notes 表新增 attachments_json 列: [{"type":"image","path":"...","description":"..."}]

工具:
  add_attachment(note_id, file) → 给已有笔记追加附件
  describe_image(note_id) → 让 AI 描述笔记中的图片内容

前端:
  笔记编辑器支持拖拽图片
  笔记详情中图片 inline 展示
```

### 7.5 代码执行工具（7.5）

#### 目标
Agent 能运行 Python 代码片段，用于数据分析、图表生成、计算验证。

#### 实现计划

```
工具:
  run_python(code: str) → 在 sandbox 中执行 Python 代码，返回 stdout/stderr

Sandbox 设计:
  - Docker 容器隔离（推荐）或 subprocess + 严格限制
  - 超时 10s
  - 内存限制 256MB
  - 禁止网络访问
  - 禁止文件系统访问（除了 /tmp）
  - 预装: numpy, pandas, matplotlib

  如果 Docker 不可用 → subprocess + 临时目录 + 资源限制
  （Windows 上用 Job Object 限制进程资源）

使用场景:
  "帮我分析这 10 条笔记的字数分布" → Agent 写 Python → 返回统计结果
  "画一张我这周的话题分布饼图" → Agent 写 matplotlib → 返回图片
```

---

## 7. Phase 7 交付清单

| # | 功能 | 优先级 | 预估 |
|---|------|--------|------|
| 7.1 | Web 搜索工具 | 🔴 | 2 天 |
| 7.2 | 日历集成 | 🟡 | 3-4 天 |
| 7.3 | 自定义工具构建器 | 🟡 | 3-4 天 |
| 7.4 | 多模态笔记 | 🟢 | 2-3 天 |
| 7.5 | 代码执行工具 | 🟢 | 2 天 |

**Phase 7 总计**：约 3–4 周（部分功能可选做）

---

## 8. Phase 8：平台化与打磨

> **目标**：从"能用的工具"变成"好用的产品"——性能、可靠性、美观度、可扩展性全面升级。
> **锚点**：性能优化 + 可观测面板 + 笔记导出 + 插件系统 + 安全 + 文档

### 8.1 性能优化（8.1）

#### 实现计划

```
后端优化:
  1. 向量搜索缓存 — 相同 query 的结果 LRU 缓存（TTL 5min）
  2. DB 连接池 — 当前每次请求 get_conn() 新建连接 → 改为连接池
     （sqlite3 本身不支持网络连接池，但可以复用单连接 + WAL 模式已启用）
  3. Agent 预热 — 启动时预加载 Agent 实例和 system prompt
  4. 流式优先 — 确保所有 LLM 调用走 streaming，不阻塞等全量返回
  5. embedding 批处理 — 多篇笔记的 embedding 合并为 batch 调用（sentence-transformers 支持）

前端优化:
  1. 虚拟滚动 — 笔记列表 > 100 条时只渲染可见区域
  2. 代码分割 — Vue Router 懒加载视图组件
  3. SSE 重连 — 指数退避 + 自动恢复
  4. 离线缓存 — Service Worker 缓存静态资源

测量:
  后端关键路径打点（search_notes / synthesize_notes / save_note 的 p50/p95/p99）
  前端 Lighthouse 评分 > 90
```

### 8.2 可观测面板（8.2）

#### 目标
一个管理后台页面，能看到系统的运行状态、成本、使用情况。

#### 实现计划

```
新增前端页面: AdminView.vue (/admin)

面板内容:
  1. 成本概览:
     - 本月/本周/今日 LLM 调用费用
     - 按模型分组（DeepSeek / GPT / Gemini）
     - 按 Agent 分组
     - 费用趋势折线图

  2. 使用统计:
     - 总笔记数 / 本月新增 / 活跃天数
     - Agent 调用次数排行
     - 工具调用次数排行
     - 每日会话数

  3. 错误监控:
     - 最近 50 条 llm_errors
     - 错误类型分布饼图
     - JSON 解析失败率趋势

  4. Eval 面板:
     - 最近一次 evals 运行结果
     - 各场景通过率趋势

  5. 系统健康:
     - 向量模型状态（已加载 / 维度 / 笔记覆盖率）
     - DB 大小
     - 内存占用

后端 API:
  GET /admin/stats  → 聚合统计数据
  GET /admin/errors → 最近错误列表
  GET /admin/health → 系统健康检查
```

### 8.3 笔记导出（8.3）

#### 目标
支持将所有笔记导出为标准格式，不锁数据。

#### 实现计划

```
导出格式:
  1. Markdown — 每篇笔记一个 .md 文件，frontmatter 包含 metadata
  2. JSON — 全量 JSON dump，包含 edges 关系
  3. ZIP — 上述格式打包下载

API:
  GET /notes/export?format=markdown → 返回 ZIP 文件
  GET /notes/export?format=json → 返回 JSON 文件

前端:
  设置页面增加"导出数据"按钮
  导出前展示预计文件大小
```

### 8.4 插件系统（8.4）

#### 目标
让系统能力可以通过插件扩展，而不是每次都要改核心代码。

#### 实现计划

```
插件类型:
  1. Agent 插件 — 注册新 Agent（如 @translator、@summarizer）
  2. Tool 插件 — 注册新工具（如 @stock_price、@news_headlines）
  3. Provider 插件 — 注册新 LLM 提供商

插件定义格式:
  my-plugin/
  ├── plugin.json      — { name, version, type, description }
  ├── agent.py         — 实现 BaseAgent 子类
  ├── tools.py         — 工具函数
  └── system_prompt.md — 可选

加载机制:
  settings.json / .env 中配置 PLUGIN_DIRS
  启动时扫描所有 plugin.json → 动态注册

优先级:
  Phase 8 做最小可用版本（Agent 插件 + Tool 插件）
  Provider 插件 + UI 市场 → 未来迭代
```

### 8.5 安全加固（8.5）

#### 实现计划

```
清单:
  1. [ ] API key 管理 — 统一从 .env 加载，日志中脱敏
  2. [ ] 输入校验 — Pydantic model 校验所有 API 入参
  3. [ ] 速率限制 — 同一 session 1 分钟最多 20 次 LLM 调用
  4. [ ] 内容过滤 — 笔记内容不存明文 API key / token
  5. [ ] DB 备份 — 自动定时备份 data/app.db
  6. [ ] 日志脱敏 — 不记录用户笔记内容到日志
  7. [ ] CSP 头 — 前端 Content-Security-Policy
  8. [ ] CORS 限制 — 只允许 localhost 访问 API
```

### 8.6 文档与引导（8.6）

#### 实现计划

```
产物:
  1. README.md 升级 — 从"开发者文档"变成"用户上手指南"
  2. 使用场景录屏 GIF — 3 个核心场景各 15s
  3. 内嵌引导 — 首次使用时前端展示 onboarding 步骤
     (1) 创建第一篇笔记 → (2) 和 AI 聊天 → (3) 查看每日回顾
  4. FAQ — 常见问题 + 答案
  5. 变更日志 — CHANGELOG.md，每个 Phase 写一条
```

---

## 8. Phase 8 交付清单

| # | 功能 | 优先级 | 预估 |
|---|------|--------|------|
| 8.1 | 性能优化 | 🟡 | 3 天 |
| 8.2 | 可观测面板 | 🟡 | 3 天 |
| 8.3 | 笔记导出 | 🟢 | 1-2 天 |
| 8.4 | 插件系统 | 🟢 | 3 天 |
| 8.5 | 安全加固 | 🔴 | 2 天 |
| 8.6 | 文档与引导 | 🟢 | 2 天 |

**Phase 8 总计**：约 2–3 周

---

## 9. 技术决策记录

### 9.1 为什么 Phase 4-8 不分更多 Phase？

```
Phase 1-3 已覆盖核心骨架：
  ✅ 单 Agent ReAct loop
  ✅ A2A 跨 Agent 接力（串行 + 并行）
  ✅ 三条记忆层（工作/情节/语义）
  ✅ 上下文智能裁剪（CC 五层金字塔）
  ✅ 模型按场景分流（3 个 provider）
  ✅ Crash recovery + 链路终止判定

Phase 4-8 是"骨架长肉"：
  Phase 4 → 让知识库更聪明（关系发现 / 可视化 / 碰撞）
  Phase 5 → 让知识来源更多元（外部导入）
  Phase 6 → 让系统更主动（推送 / 缺口 / 提醒）
  Phase 7 → 让 Agent 更能干（Web / 日历 / 代码 / 自定义）
  Phase 8 → 让产品更成熟（性能 / 安全 / 文档）

每个 Phase 2-3 周，刚好在个人业余项目的可持续节奏内。
再细分会导致 Phase 过多、每个 Phase 内容太少、retro 开销太大。
```

### 9.2 关键技术选型

| 场景 | 选型 | 理由 |
|------|------|------|
| 图谱可视化 | D3.js force simulation | 轻量，不引入图数据库 |
| Web 正文提取 | trafilatura | 纯 Python，比 readability 更准 |
| Web 搜索 (Phase 5) | DuckDuckGo | 零成本，够用 |
| Web 搜索 (Phase 7) | Tavily | 专为 AI Agent 设计，返回结构化结果 |
| 日历协议 | CalDAV | 支持 Google/Apple/Nextcloud |
| 代码执行沙箱 | Docker 容器 | 隔离性好；不可用时降级 subprocess |
| 定时任务 | OS cron / Task Scheduler | 简单可靠，不比在 Python 进程内调度差 |

### 9.3 不做的事（明确边界）

```
Phase 4-8 不做:
  ✗ 多用户支持 — 这是个人知识工作台，不是 SaaS
  ✗ 协作编辑 — 同上
  ✗ 云端同步 — 本地 SQLite + 文件系统就够
  ✗ OAuth / 第三方登录 — 本地单用户，不需要
  ✗ 移动 App — Web 响应式就够
  ✗ 语音输入（实时 STT）— Whisper 离线可做但 ROI 低
  ✗ 向量数据库迁移（pgvector / Qdrant）— sqlite-vec 够用至少到 1 万条笔记
  ✗ 微服务拆分 — 单体 FastAPI 够用到 10 万笔记
  ✗ 自训练 embedding 模型 — sentence-transformers 预训练模型够用
```

---

## 10. 风险与依赖

### 10.1 技术风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| sqlite-vec 性能退化 >1 万笔记 | 语义搜索变慢 | 加 LRU 缓存；监控相似度搜索耗时 |
| sentence-transformers 内存占用 | 低内存机器跑不动 | 支持配置轻量模型（如 all-MiniLM-L6-v2，80MB） |
| LLM API 涨价 | 成本上升 | 缓存 + cheap model 分流 + 本地模型预留接口 |
| Tavily / Brave API 收费变更 | 外部搜索不可用 | 保留 DuckDuckGo fallback |
| Windows 兼容性（Docker 不可用） | 代码执行沙箱缺失 | subprocess + Job Object 降级方案 |

### 10.2 节奏风险

| 风险 | 缓解 |
|------|------|
| 业余时间不足 | 每个 Phase 拆成独立可交付的小功能，随时可以暂停 |
| 方向漂移（做着做着跑偏了） | 每个 Phase 结束写 retro，对照本计划书校正 |
| 过度工程化（在不需要的地方花太多时间） | 9.3 明确"不做的事"；每个功能先问"有没有更简单的方案" |

### 10.3 依赖

```
外部服务:
  - DeepSeek API   — Phase 4-8 持续依赖（主模型）
  - OpenAI API     — Phase 4-8 持续依赖（ReviewAgent）
  - Google AI API  — Phase 4-8 持续依赖（BrainAgent）
  - Tavily API     — Phase 7 新增（Web 搜索）
  - CalDAV 服务    — Phase 7 可选（日历）

内部依赖:
  - Phase 4 不依赖 Phase 5-8（独立可交付）
  - Phase 5 的 web_search 工具被 Phase 7.1 升级
  - Phase 6 的每日推送依赖 Phase 4.5 的 Daily Digest 2.0
  - Phase 7.3 自定义工具架构被 Phase 8.4 插件系统复用
  - Phase 8 贯穿所有 Phase（持续优化）
```

---

## 附录 A：与 Clowder 的对标

本项目从 Clowder 学到了 LLM 工程基线（context-transport / verdict-detect / MultiMentionOrchestrator / WorklistRegistry），Phase 4-8 则走出自己的路：

| 能力 | Clowder | 本项目 Phase 4-8 |
|------|---------|-----------------|
| 知识图谱 | ❌ 没有 | ✅ Phase 4 核心差异化能力 |
| 外部知识导入 | ✅ Web clipper | ✅ Phase 5 |
| 主动推送 | ✅ Daily digest | ✅ Phase 6 升级 |
| 代码执行 | ✅ Code Interpreter | ✅ Phase 7.5 |
| 插件系统 | ✅ Plugin market | ✅ Phase 8.4（最小可用版） |
| 多模态 | ✅ 图片理解 | ✅ Phase 7.4 |
| 间隔复习 | ❌ 没有 | ✅ Phase 6.3 差异化能力 |
| Idea Collision | ❌ 没有 | ✅ Phase 4.3 差异化能力 |

三条差异化主线：
1. **知识生长**（Phase 4）— 不是存了就忘，而是让笔记之间自动产生联系
2. **主动智能**（Phase 6）— 不等你问，系统先提醒你该复习/该探索什么
3. **安全打磨**（Phase 8）— 从"能跑"到"好用"

---

## 附录 B：Schema 演进总览

```
Phase 1-3 (9 表):
  notes, notes_fts, messages, daily_digests,
  llm_calls, llm_errors, eval_runs, embedding_meta,
  edges, worklist

Phase 4 新增:
  pending_suggestions  — 关系建议（待用户确认）
  idea_collisions      — 意外关联发现
  tag_aliases          — 标签同义词

Phase 5 新增:
  source_trace         — 外部来源追踪

Phase 6 新增列（notes 表）:
  last_reviewed_at     — 最后复习时间
  review_interval      — 复习间隔
  review_count         — 复习次数

Phase 7 新增:
  custom_tools         — 用户自定义工具
  notes.attachments_json — 多模态附件

Phase 8 无新增 schema（优化+打磨阶段）
```

---

> **下一步**：按 Phase 4.1 开始——关系图谱自动发现。这个计划书写好之后，我会按顺序逐个 Phase 提交 PR。
>
> 🤖 Generated with [Claude Code](https://claude.com/claude-code)
