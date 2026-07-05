# 前端商用级改造方案：AI Thought Studio

> 目标：把当前前端从“能用的多 Agent 聊天界面”升级为“有商业产品质感的个人 AI 知识工作台”。  
> 关键词：高级、安静、可信、可解释、有掌控感。

## 1. 重新判断问题

上一版 `Thought Cockpit` 的问题是：  
它解释了功能区，却没有真正解决“第一眼不好看、交互不丝滑、不像成熟产品”的问题。

商用及格线不是“功能都摆出来”，而是：

1. 用户第一眼知道这是一个完整产品，不是 Demo
2. 主要操作路径短、清楚、不打断思考
3. AI 的复杂过程被优雅折叠，而不是暴露成日志
4. 页面有视觉重心，不是三栏信息堆积
5. 空状态、加载态、错误态都有设计感
6. Agent、工具、笔记之间的关系能被感知，但不吵

因此新版方向不叫 Cockpit。  
Cockpit 容易做成复杂仪表盘。

建议改成：

> **AI Thought Studio**

它更像一个高级写作 / 研究 / 知识沉淀空间。

## 2. 产品气质

### 2.1 不要像什么

不要像：

- 开发者控制台
- 普通 ChatGPT 套壳
- Notion 的廉价仿制
- 三栏后台管理系统
- Agent 日志播放器

### 2.2 要像什么

可以参考这些气质：

- Linear：克制、锐利、节奏快
- Raycast：命令感强、快捷、轻盈
- Arc：空间感、边栏清楚、细节精致
- Notion AI：低打扰、内容优先
- Superhuman：键盘优先、反馈爽

### 2.3 核心体验句

> 用户把一个碎片想法扔进来，界面像一个安静但聪明的工作室：帮他保存、连接、挑战、扩写，并把过程整理成可继续工作的对象。

## 3. 信息架构重做

不要默认三栏常驻。  
三栏会显得重，也会让首屏像后台系统。

推荐采用：

```text
┌─────────────────────────────────────────────────────────────┐
│ Global Top Bar                                              │
├───────────────┬─────────────────────────────────────────────┤
│ Left Rail     │ Main Studio                                 │
│               │                                             │
│ Spaces        │ Thought Thread                              │
│ Recent Notes  │ Composer                                    │
│ Daily Digest  │                                             │
│               │ Right Insight Drawer 按需滑出               │
└───────────────┴─────────────────────────────────────────────┘
```

核心变化：

- 左侧只保留导航和轻量记忆入口
- 中间成为绝对主角
- 右侧上下文不常驻，改成按需滑出的 Insight Drawer
- 工具和 Agent 过程折叠在消息内部，而不是抢占布局

## 4. 首屏设计

### 4.1 顶部栏

顶部栏应该非常轻：

```text
AI Thought Studio       Today: 14 notes · 3 themes      ⌘K
```

包含：

- 产品名或当前空间名
- 今日状态摘要
- 命令菜单入口
- 设置 / 模型状态放右侧二级入口，不要抢眼

不要在顶部塞满按钮。

### 4.2 左侧 Rail

左侧宽度建议：`248px`

结构：

```text
New Thought        +

Studio
├─ Inbox
├─ Threads
├─ Notes
├─ Daily Review
└─ Archive

Agents
├─ Knowledge
├─ Review
└─ Brain

Recent
├─ 前端交互为什么不像产品
├─ 多 Agent 不是自主路由
└─ 个人知识系统的记忆层
```

设计要求：

- 左侧是“空间导航”，不是笔记数据库
- 最近笔记最多显示 5 条
- Agent 状态只做轻量入口，不做大头像
- 当前选中项要有柔和高亮

### 4.3 中间主区域

主区域不是聊天气泡，而是 `Thread + Studio Composer`。

推荐宽度：

- 内容最大宽度：`760px`
- 整体居中
- 大屏时右侧留给 Drawer

```text
┌──────────────────────────────────────┐
│ Thread Title / 自动摘要               │
│ subtle metadata                       │
├──────────────────────────────────────┤
│ User Thought                          │
│ AI Response Block                     │
│ Insight Chips                         │
│ Agent Trace collapsed                 │
├──────────────────────────────────────┤
│ Composer                              │
└──────────────────────────────────────┘
```

## 5. 视觉系统

### 5.1 总体风格

建议用“深色高级 SaaS”作为默认主题。

不是纯黑，而是 warm dark：

```text
App Background:      #0D0E12
Surface Base:        #13151B
Surface Raised:      #191C24
Surface Hover:       #20242E
Border Subtle:       rgba(255,255,255,0.07)
Border Strong:       rgba(255,255,255,0.13)
Text Primary:        #F4F1EA
Text Secondary:      #A9A29A
Text Tertiary:       #6F767E
```

原因：

- 纯黑容易廉价
- 纯灰容易后台感
- warm dark 更适合知识、写作、思考

### 5.2 品牌强调色

不要用很多彩虹色。  
主强调色建议只用一个：

```text
Brand:        #8B7CFF
Brand Soft:   rgba(139,124,255,0.14)
Brand Border: rgba(139,124,255,0.35)
```

Agent 颜色只作为细线和小圆点使用：

```text
Knowledge: #6EA8FF
Review:    #FFB86C
Brain:     #B892FF
```

不要把 Agent 卡片做成大面积彩色，会显得幼稚。

### 5.3 字体层级

```text
Page Title:      20px / 28px / 600
Thread Title:    18px / 26px / 600
Body:            15px / 24px / 400
Small:           13px / 18px / 400
Micro:           11px / 14px / 500
```

内容区行高要足够大。  
这是知识类产品质感的关键。

### 5.4 圆角和阴影

```text
Small radius:  8px
Card radius:   14px
Panel radius:  18px
Composer:      22px
```

阴影不要重：

```text
0 12px 40px rgba(0,0,0,0.28)
0 1px 0 rgba(255,255,255,0.04) inset
```

商业感来自边界、留白、层次，不来自大阴影。

## 6. 核心交互：从聊天框变成 Thought Composer

### 6.1 Composer 设计

底部输入区是最重要的商业化触点。

设计成浮动胶囊卡片：

```text
┌──────────────────────────────────────────────────┐
│ Write a thought, question, or fragment...         │
│                                                  │
│ + Attach   # Tag   @ Agent        Save  Review ↵ │
└──────────────────────────────────────────────────┘
```

中文版本：

```text
┌──────────────────────────────────────────────────┐
│ 写下一个想法、问题或碎片……                         │
│                                                  │
│ + 附件   # 标签   @ Agent        保存  挑战 发送   │
└──────────────────────────────────────────────────┘
```

### 6.2 输入后的智能动作

用户输入时，右侧或输入框上方出现轻量建议：

```text
Suggested:
[保存为笔记] [让 Review 挑战] [让 Brain 发散] [找相似想法]
```

规则：

- 用户输入较短碎片：优先显示“保存为笔记”
- 用户输入判断句：显示“让 Review 挑战”
- 用户输入概念或灵感：显示“让 Brain 发散”
- 用户输入“总结/整理/合成”：显示“合成相关笔记”

这会让产品显得聪明，而不是只会等待提交。

### 6.3 发送后的交互节奏

不要直接出现一大段 loading。

推荐三段式：

```text
1. Capturing thought...
2. Searching memory...
3. Composing response...
```

中文：

```text
正在捕捉想法……
正在检索记忆……
正在组织回应……
```

如果触发多 Agent：

```text
Knowledge is reading memory
Review is checking assumptions
Brain is exploring adjacent ideas
```

这里用一行小状态即可，不要铺满屏幕。

## 7. 消息设计：不要聊天气泡

聊天气泡会让产品降级成 IM。

建议使用“文档块”：

```text
User Thought
────────────────
我感觉前端交互很一般，不具备商用及格线。

AI Response
────────────────
你这个判断是对的。问题不在功能，而在……
```

### 7.1 AI 回复块结构

```text
┌──────────────────────────────────────────┐
│ AI Response                              │
│                                          │
│ 正文内容                                  │
│                                          │
│ ┌ Insight Chips ┐                        │
│ [3 related notes] [Review found 2 risks] │
│                                          │
│ Agent Trace ▸                            │
└──────────────────────────────────────────┘
```

### 7.2 Insight Chips

这是商业质感的关键。

不要把复杂事件外露，而是变成 chips：

```text
[引用 4 条笔记] [发现 2 个假设] [生成 3 个方向] [已保存]
```

点击 chip 打开 Drawer。

### 7.3 Agent Trace

默认折叠：

```text
Agent Trace ▸ Knowledge → Review → Brain · natural_end
```

展开后才显示：

```text
Knowledge
- 检索相关笔记
- 整理上下文

Review
- 发现“功能等于体验”的隐含假设
- 提出商业及格线标准

Brain
- 给出 Studio / Inbox / Composer 隐喻
```

注意：  
这里仍然要诚实命名为 Handoff / Trace，不要叫 Autonomous Routing。

## 8. Insight Drawer

右侧不常驻。  
点击 chip、笔记引用、Agent Trace 后滑出。

宽度建议：`420px`

```text
┌──────────────────────────────┐
│ Related Notes            Esc │
├──────────────────────────────┤
│ Note Card                    │
│ Why it matters               │
│ Actions                      │
├──────────────────────────────┤
│ Note Card                    │
│ Why it matters               │
│ Actions                      │
└──────────────────────────────┘
```

### 8.1 Drawer 类型

至少四种：

1. Related Notes
2. Review Findings
3. Brain Expansions
4. Tool Details

### 8.2 Drawer 动作

每个 Drawer 都必须有可执行动作：

- 用这条笔记继续追问
- 保存为新笔记
- 替代旧笔记
- 归档
- 复制
- 打开详情

没有动作的 Drawer 只是信息堆积。

## 9. Notes 页面改造

Notes 不要做成普通表格。

推荐做成“知识卡片墙 + 筛选侧栏”：

```text
Notes
├─ Search
├─ Filters: Live / Superseded / Archived
├─ Tags
└─ Cards
```

### 9.1 Note Card

```text
┌────────────────────────────────────┐
│ Live                    #product   │
│ 前端不是功能展示，而是能力显形……     │
│                                    │
│ Related: 4 · Used: 2 · Jun 22      │
└────────────────────────────────────┘
```

### 9.2 Superseded 状态

这是你项目的特色，应该设计出来。

```text
Superseded
这条想法已被「AI Thought Studio 交互原则」替代
```

点击可以看到演化链：

```text
Old Note → New Note → Current Synthesis
```

这是普通笔记产品没有的亮点。

## 10. Daily Review 页面

Daily Review 可以做成真正有价值的商业功能。

不要只是摘要。

推荐结构：

```text
Daily Review
├─ Today in one sentence
├─ Repeated Themes
├─ New Signals
├─ Tensions
├─ Suggested Next Thoughts
└─ Actions
```

### 10.1 示例

```text
Today in one sentence
你今天的注意力从“多 Agent 架构完成”转向了“产品体验是否成立”。

Repeated Themes
- 前端交互
- 商用及格线
- Agent 能力显形

New Signal
- 你开始用产品经理视角审视系统，而不是工程验收视角

Tensions
- 后端能力已经复杂，但用户可能仍然只看到一个聊天框

Suggested Next Thoughts
- 什么样的交互能让 ReviewAgent 的价值一眼可见？
- 哪些信息应该折叠，哪些必须显性？
```

### 10.2 商业化价值

Daily Review 是留存功能。  
它让用户第二天有理由回来。

顶部可以显示：

```text
3 themes emerged today
```

而不是普通红点。

## 11. 命令菜单

必须加 `Cmd/Ctrl + K`。

这是高级工具的“手感中枢”。

命令示例：

```text
New thought
Search notes
Ask Knowledge
Challenge with Review
Expand with Brain
Synthesize selected notes
Open Daily Review
Archive current note
```

命令菜单能显著提升产品质感，因为它让复杂功能不必都摊在界面上。

## 12. 微交互

### 12.1 Hover

卡片 hover：

- 背景轻微变亮
- 边框出现 brand soft
- 操作按钮淡入

不要大幅移动。

### 12.2 Loading

用 skeleton 和阶段文案，不要转圈圈。

```text
Searching memory...
```

配合一条细进度光带。

### 12.3 保存成功

不要弹大 toast。

在输入框或消息块右上角出现：

```text
Saved to Notes
```

1.8 秒后消失。

### 12.4 Agent 切换

Agent 切换不要大动画。  
用细线和短文案：

```text
Review joined to challenge assumptions
```

中文：

```text
Review 正在检查这个想法的隐含假设
```

### 12.5 Drawer 打开

Drawer 从右侧滑入，背景轻微压暗，但不要遮挡主内容。

动画：

```text
duration: 180ms
easing: cubic-bezier(.2,.8,.2,1)
```

## 13. 空状态设计

空状态决定产品是否像 Demo。

### 13.1 首页空状态

```text
What are you thinking about?

Drop a fragment. I’ll help you save it, challenge it, or connect it to what you already know.

[Start with a thought...]
```

中文：

```text
你现在在想什么？

丢进一个碎片想法。我会帮你保存、挑战它，或连接到你已有的笔记。
```

### 13.2 Notes 空状态

```text
Your knowledge base starts with one honest fragment.
```

中文：

```text
你的知识库，从一个真实的碎片想法开始。
```

### 13.3 搜索无结果

```text
No related notes found.
This may be a new direction worth saving.
```

中文：

```text
没有找到相关笔记。
这可能是一个值得保存的新方向。
```

## 14. 移动端策略

不要硬塞三栏。

移动端采用：

```text
Main Thread
Bottom Composer
Drawer full-screen
Left Rail becomes command menu
```

底部导航：

```text
Studio · Notes · Review · Search
```

移动端优先保证：

- 快速捕捉
- 查看最近线程
- 保存为笔记
- 打开 Daily Review

复杂 Agent Trace 可以折叠更深。

## 15. MVP 优先级

### P0：立刻提升商业质感

1. 主界面从聊天气泡改成文档块
2. Composer 改成浮动胶囊输入区
3. Agent / Tool 事件改成 Insight Chips
4. 右侧上下文改成按需 Drawer
5. 加入统一深色视觉系统

### P1：提升产品辨识度

1. Daily Review 做成独立高级页面
2. Notes 加入状态演化链
3. Cmd/Ctrl + K 命令菜单
4. 输入时智能建议动作
5. Handoff Trace 优雅折叠

### P2：提升长期留存

1. 每周主题回顾
2. 个人知识画像
3. 主动提出“值得继续想”的问题
4. 外部 PDF / 网页导入
5. 主题级 synthesis 页面

## 16. 推荐组件结构

```text
AppShell.vue
├─ GlobalTopBar.vue
├─ LeftRail.vue
├─ StudioView.vue
│  ├─ ThreadHeader.vue
│  ├─ ThoughtBlock.vue
│  ├─ AIResponseBlock.vue
│  ├─ InsightChips.vue
│  ├─ AgentTrace.vue
│  └─ ThoughtComposer.vue
├─ InsightDrawer.vue
│  ├─ RelatedNotesPanel.vue
│  ├─ ReviewFindingsPanel.vue
│  ├─ BrainExpansionsPanel.vue
│  └─ ToolDetailsPanel.vue
├─ NotesView.vue
│  ├─ NotesToolbar.vue
│  ├─ NoteCardGrid.vue
│  └─ NoteEvolutionChain.vue
├─ DailyReviewView.vue
└─ CommandMenu.vue
```

## 17. 数据映射

| UI 模块 | 数据来源 |
|---|---|
| Thread Block | messages / session history |
| Insight Chips | SSE events 聚合 |
| Agent Trace | orchestrator / router / verdict |
| Related Notes | search_notes / context assemble |
| Review Findings | ReviewAgent 输出解析 |
| Brain Expansions | BrainAgent 输出解析 |
| Tool Details | tool_start / tool_end |
| Notes Grid | notes 表 |
| Evolution Chain | status / superseded_by |
| Daily Review | daily digest trend detection |

## 18. 商用及格验收标准

这一版前端是否及格，不看“功能有没有”，看下面这些：

1. 首屏截图能不能让人觉得这是一个认真产品
2. 用户是否能在 3 秒内知道下一步能做什么
3. AI 过程是否清楚但不吵
4. Agent 能力是否被感知，而不是藏在日志里
5. 笔记状态是否体现“知识会演化”
6. Daily Review 是否让用户愿意第二天回来
7. 输入体验是否比普通 textarea 更有掌控感
8. 空状态是否有产品气质

## 19. 最推荐的第一版落地范围

如果只做一轮，我建议只做这 5 件事：

1. **重做 AppShell**：左 Rail + 中间 Studio + 右 Drawer
2. **重做 Composer**：浮动胶囊输入 + 快捷动作
3. **重做消息样式**：文档块替代聊天气泡
4. **事件变 Chips**：工具 / Agent / 引用都折叠成可点 chips
5. **统一视觉系统**：warm dark + 统一圆角 / 间距 / 字体层级

这 5 件事完成后，即使后端不变，产品观感也会从 Demo 提升到可展示版本。

## 20. 一句话结论

上一版是“把能力摆出来”。  
这一版应该是“把复杂能力收进一个安静、漂亮、可掌控的思考空间里”。

真正的商用感来自：

> 少展示系统有多复杂，多让用户感觉自己更会思考。

