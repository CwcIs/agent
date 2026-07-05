# 前端交互改造方案：Thought Cockpit

> 目标：把当前前端从“普通聊天界面”升级为“多 Agent 知识工作台”。  
> 核心不是变漂亮，而是让用户清楚感知：想法如何被捕捉、检索、挑战、联想、沉淀。

## 1. 设计判断

当前系统的后端能力已经比较强：

- 笔记有 `live / superseded / archived` 状态
- 有 FTS + 向量检索
- 有 KnowledgeAgent / ReviewAgent / BrainAgent
- 有 `@agent` prompt-chained handoff
- 有工具调用事件、SSE 流式输出、多 Agent 并行渲染基础
- 有每日回顾趋势检测

但如果前端仍然主要表现为“一个聊天框 + 一串消息”，用户会感受不到这些能力。

因此前端应该把隐藏能力显性化：

- AI 为什么这么回答
- 它用了哪些笔记
- 哪个 Agent 正在参与
- 当前想法处于什么状态
- 哪些旧想法被连接、挑战或替代

## 2. 产品隐喻

建议采用：

> **Thought Cockpit：思考驾驶舱**

用户不是在“跟机器人聊天”，而是在驾驶自己的知识系统。

三个核心区域：

1. **Memory Stream**：左侧记忆流
2. **Thinking Canvas**：中间思考画布
3. **Context Radar**：右侧上下文雷达

## 3. 总体布局

```text
┌──────────────────────────────────────────────────────────────┐
│ Top Bar: 当前 Session / Agent 状态 / Daily Digest Badge       │
├───────────────┬────────────────────────────┬─────────────────┤
│ Memory Stream │ Thinking Canvas            │ Context Radar   │
│               │                            │                 │
│ 最近笔记       │ 用户输入 / AI 回复           │ 相关笔记         │
│ 今日捕捉       │ Agent 分段                  │ 冲突观点         │
│ 标签筛选       │ Tool 卡片                   │ 联想扩展         │
│ 状态筛选       │ Handoff Timeline            │ 可合成主题       │
├───────────────┴────────────────────────────┴─────────────────┤
│ Quick Capture Bar: 保存 / 挑战 / 联想 / 合成                  │
└──────────────────────────────────────────────────────────────┘
```

## 4. 左侧：Memory Stream

### 4.1 作用

左侧不是传统“笔记列表”，而是用户的思想收件箱。

它回答：

- 我最近捕捉了什么？
- 哪些想法还活着？
- 哪些想法已经被替代？
- 哪些主题最近反复出现？

### 4.2 信息结构

建议分为四组：

```text
Memory Stream
├─ Today
│  ├─ 今天新增的笔记
│  └─ 今天被 AI 引用过的笔记
├─ Active Ideas
│  ├─ live 状态笔记
│  └─ 最近更新优先
├─ Evolving
│  ├─ superseded 笔记
│  └─ 显示 “被哪条笔记替代”
└─ Archived
   └─ 手动归档内容，默认折叠
```

### 4.3 卡片设计

每条笔记卡片包含：

- 标题或首行摘要
- 状态 badge：`Live` / `Superseded` / `Archived`
- 标签：如 `#review`、`#brain`
- 最近被引用次数
- 最后更新时间

示例：

```text
┌────────────────────────────┐
│ Live · #product #agent     │
│ AI 工作台不是聊天框，而是... │
│ 引用 3 次 · 2 小时前         │
└────────────────────────────┘
```

## 5. 中间：Thinking Canvas

### 5.1 作用

中间仍然是主工作区，但不应该只是聊天记录。

它应该呈现一次思考是如何展开的：

```text
用户想法
↓
KnowledgeAgent 检索和整理
↓
ReviewAgent 挑战假设
↓
BrainAgent 发散联想
↓
最终沉淀 / 保存 / 归档 / 替代
```

### 5.2 Agent 分段

不同 Agent 的输出用轻量分隔条展示：

```text
━━ Knowledge · 正在整理相关记忆 ━━
这里是知识整理回复……

━━ Review · 正在挑战你的假设 ━━
这里是批判性反馈……

━━ Brain · 正在做联想扩展 ━━
这里是发散想法……
```

重点：  
不要把 Agent 做成“炫技动画”，而是让用户理解每个角色的职责。

### 5.3 Tool 调用卡片

工具调用默认折叠，用自然语言表达，不展示底层噪音。

```text
▸ 检索了 5 条相关笔记
▸ 合成了 3 个主题
▸ 保存为新笔记
```

展开后显示：

- 工具名称
- 输入摘要
- 输出摘要
- 关联笔记
- 耗时

### 5.4 Handoff Timeline

因为项目里 A2A 不是“Agent 自主路由”，而是 prompt-chained handoff，所以前端也应诚实表达。

推荐叫：

> **Handoff Chain**

不要叫：

> Autonomous Agent Routing

展示形式：

```text
Knowledge → Review → Brain
```

或：

```text
Knowledge 触发 @review
Review 触发 @brain
Brain 自然结束
```

配合 verdict：

- `natural_end`：自然结束
- `missing_handoff`：提到需要别人但没有明确 `@agent`
- `loop_detected`：检测到循环

## 6. 右侧：Context Radar

### 6.1 作用

右侧是当前思考的雷达，而不是普通详情栏。

它回答：

- AI 参考了哪些旧笔记？
- 有哪些相似想法？
- 有哪些冲突观点？
- 有哪些可合成主题？
- 这条新想法可能替代哪条旧想法？

### 6.2 面板结构

```text
Context Radar
├─ Referenced Notes
│  └─ 当前回答实际引用的笔记
├─ Similar Ideas
│  └─ 向量检索召回的相似笔记
├─ Tensions
│  └─ ReviewAgent 发现的矛盾或盲点
├─ Expansions
│  └─ BrainAgent 的联想方向
└─ Actions
   ├─ 保存为笔记
   ├─ 替代旧笔记
   ├─ 加入每日回顾
   └─ 继续追问
```

### 6.3 点击行为

用户点击 AI 回复中的笔记引用时：

- 右侧打开对应笔记
- 高亮它为什么相关
- 显示可执行动作：
  - 编辑
  - 归档
  - 标记为被替代
  - 用它继续追问

## 7. 底部：Quick Capture Bar

### 7.1 作用

这是最重要的输入入口。

用户很多时候不是想“聊天”，而是想快速扔进一个碎片念头。

底部输入栏应该支持四个动作：

```text
[ 输入一个想法……                         ]
[保存] [挑战] [联想] [合成]
```

### 7.2 动作语义

| 动作 | 触发逻辑 | 用户感受 |
|---|---|---|
| 保存 | `save_note` | 把碎片收进系统 |
| 挑战 | `#review` 或 `@review` | 让 AI 反驳我 |
| 联想 | `@brain` | 帮我扩展可能性 |
| 合成 | `synthesize_notes` | 把相关笔记压成结构 |

### 7.3 快捷键

建议：

- `Cmd/Ctrl + Enter`：发送
- `Cmd/Ctrl + S`：保存为笔记
- `Cmd/Ctrl + R`：挑战
- `Cmd/Ctrl + B`：联想
- `Cmd/Ctrl + K`：打开命令菜单

## 8. Daily Digest 入口

每日回顾不应该只是一个页面或按钮，而应该变成顶部状态提醒。

示例：

```text
Today: 12 notes · 3 repeated themes · 1 anomaly
```

点击后打开 Daily Digest 面板：

```text
今日趋势
├─ 反复出现：Agent UI、知识沉淀、个人工作流
├─ 异常变化：今天大量出现“前端交互”相关内容
├─ 建议追问：你是不是在从后端能力转向产品体验？
└─ 可操作：
   ├─ 生成今日总结
   ├─ 合成一个主题笔记
   └─ 明天提醒我继续这个方向
```

## 9. 视觉风格

建议关键词：

- 安静
- 深色但不压抑
- 卡片轻
- 状态清楚
- Agent 有角色感但不拟人过度

### 9.1 配色建议

```text
Background: #0F1115
Panel:      #171A21
Card:       #20242D
Border:     #2C3240
Text Main:  #F4F6FA
Text Muted: #9AA4B2

Knowledge:  #7C9CFF
Review:     #FFB86B
Brain:      #B88CFF
Success:    #70E0A3
Warning:    #FFD166
Danger:     #FF6B6B
```

### 9.2 Agent 颜色

| Agent | 颜色 | 气质 |
|---|---|---|
| KnowledgeAgent | 蓝色 | 稳定、整理、检索 |
| ReviewAgent | 橙色 | 挑战、反思、批判 |
| BrainAgent | 紫色 | 发散、联想、创造 |

## 10. 核心页面状态

### 10.1 空状态

不要显示“暂无消息”。

建议显示：

```text
今天你想捕捉什么？

你可以：
- 丢进一个碎片想法
- 让 ReviewAgent 挑战它
- 让 BrainAgent 发散它
- 从旧笔记里合成一个主题
```

### 10.2 流式生成中

展示当前阶段，而不是只有 loading。

```text
Knowledge 正在检索相关记忆……
Review 正在寻找假设漏洞……
Brain 正在扩展相邻想法……
```

### 10.3 无召回结果

不要说“没有结果”。

建议：

```text
这可能是一个新方向。
要不要把它保存为第一条相关笔记？
```

### 10.4 循环检测

当 `loop_detected` 出现时，前端应该温和解释：

```text
这条 Handoff Chain 似乎绕回来了。
我已停止继续调度，避免 Agent 之间空转。
```

## 11. MVP 实施顺序

### Step 1：布局重构

先做三栏布局：

- 左侧 Memory Stream
- 中间 Thinking Canvas
- 右侧 Context Radar

不急着改数据结构，可以先用现有 notes / messages / events。

### Step 2：Agent 分段

把现有 SSE 事件中的 Agent 信息视觉化：

- Agent 分隔条
- Agent badge
- 并行状态提示

这是最能立刻提升“多 Agent 感知”的部分。

### Step 3：Tool 卡片

把 `tool_start` / `tool_end` 做成可折叠卡片。

默认只显示一句人话：

```text
检索了 5 条相关笔记
```

而不是直接暴露技术日志。

### Step 4：Context Radar

先展示：

- 当前相关笔记
- 点击预览
- 保存 / 归档 / 编辑动作

后续再加冲突观点、联想方向、替代建议。

### Step 5：Quick Capture

把底部输入升级为动作入口：

- 保存
- 挑战
- 联想
- 合成

这一步会明显改变用户使用方式。

## 12. 推荐组件拆分

```text
AppShell.vue
├─ TopStatusBar.vue
├─ MemoryStream.vue
│  ├─ MemorySection.vue
│  └─ NoteCard.vue
├─ ThinkingCanvas.vue
│  ├─ MessageBlock.vue
│  ├─ AgentDivider.vue
│  ├─ ToolCallCard.vue
│  └─ HandoffTimeline.vue
├─ ContextRadar.vue
│  ├─ ReferencedNotes.vue
│  ├─ SimilarIdeas.vue
│  ├─ TensionList.vue
│  └─ ContextActions.vue
└─ QuickCaptureBar.vue
```

## 13. 与现有后端能力的映射

| 前端能力 | 后端/数据来源 |
|---|---|
| Agent 分段 | SSE event 中的 agent_id |
| 工具卡片 | `tool_start` / `tool_end` |
| Handoff Chain | router / orchestrator / verdict |
| 相关笔记 | `search_notes` / context assemble |
| 保存笔记 | `save_note` |
| 编辑/删除/归档 | PATCH / DELETE `/notes/:id` |
| 合成主题 | `synthesize_notes` |
| 每日趋势 | daily digest `_detect_trends()` |

## 14. 最小可用验收标准

第一版改造完成后，应满足：

- 用户能一眼看出当前有哪些 Agent 参与
- 用户能看懂 AI 使用了哪些工具
- 用户能从 AI 回复跳到相关笔记
- 用户能快速保存、挑战、联想一个想法
- 用户能理解一次 handoff 是如何发生和结束的
- 页面看起来像知识工作台，而不是普通聊天套壳

## 15. 一句话总结

前端改造的关键不是“更像 ChatGPT”，而是更像一个能显示思考过程的知识驾驶舱：

> 左边是记忆，中间是思考，右边是联想与质疑，底部是新的想法入口。

