"""
08-checkpointer.py — 跨请求多轮对话（MemorySaver）
====================================================
学习目标：给 07 的图加一行 checkpointer，让同一个 thread 的对话跨 invoke 保持记忆。

07 的问题：
  graph.invoke(state1)  ← 第一次问
  graph.invoke(state2)  ← 第二次问，模型完全不记得第一次

08 加了 checkpointer 之后：
  config = {"configurable": {"thread_id": "alice"}}
  graph.invoke({"messages": [msg1]}, config)  ← 第一次
  graph.invoke({"messages": [msg2]}, config)  ← 第二次，自动拼上第一次历史

为什么这对 Phase 1 重要？
  packages/api 里的 /chat/stream 端点要支持多轮对话。
  不用 checkpointer 的话你得自己把历史消息从 DB 拉出来每次都塞进去。
  用了 checkpointer，框架帮你管，你只需传 thread_id。

MemorySaver vs SqliteSaver：
  MemorySaver  — 存在内存，进程重启就没了，适合 playground 和测试
  SqliteSaver  — 存在 SQLite，进程重启可恢复，Phase 1 生产用这个
  （SqliteSaver 需要 langgraph-checkpoint-sqlite 包）

对比表（在 07 基础上更新）
──────────────────────────────────────────────────────────────
              03 手写        07 LangGraph       08 +checkpointer
──────────────────────────────────────────────────────────────
循环控制      手写 for       框架               框架
状态管理      messages 列表  TypedDict          TypedDict
工具分发      if/else        ToolNode           ToolNode
中断/恢复     ❌             ❌                 ✅ thread_id
多轮记忆      ❌             ❌                 ✅ 自动拼历史
可视化        ❌             draw_ascii()       draw_ascii()
──────────────────────────────────────────────────────────────
"""
import os, json
from typing import Annotated
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver   # ← 新增
from typing_extensions import TypedDict

load_dotenv()

# ========== 模拟知识库 ==========
KNOWN_NOTES = [
    {"title": "B端优先级", "content": "Q3 应该先做 B 端，收入能养活 C 端增长。"},
    {"title": "技术债清单", "content": "老登录模块耦合太深，测试覆盖率不到 30%。"},
]

@tool
def search(query: str) -> str:
    """搜索知识库中的笔记"""
    results = [n for n in KNOWN_NOTES if query in n["title"] or query in n["content"]]
    return json.dumps(results, ensure_ascii=False)

@tool
def save_note(title: str, content: str, tags: str = "") -> str:
    """保存一条新笔记到知识库"""
    note = {"title": title, "content": content, "tags": tags}
    KNOWN_NOTES.append(note)
    return json.dumps({"status": "ok"}, ensure_ascii=False)

TOOLS = [search, save_note]

llm = ChatOpenAI(
    model="deepseek-chat",
    openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
    openai_api_base="https://api.deepseek.com",
    max_tokens=500,
).bind_tools(TOOLS)

SYSTEM_PROMPT = "你用中文回答。需要查资料时调 search，用户要求保存时调 save_note。"

class State(TypedDict):
    messages: Annotated[list, add_messages]

def call_llm(state: State) -> dict:
    msgs = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    return {"messages": [llm.invoke(msgs)]}

def should_continue(state: State) -> str:
    last = state["messages"][-1]
    return "tools" if last.tool_calls else END

# ========== 构图（唯一变化：加 checkpointer）==========
checkpointer = MemorySaver()   # ← 内存存档，进程内有效

graph = (
    StateGraph(State)
    .add_node("llm", call_llm)
    .add_node("tools", ToolNode(TOOLS))
    .set_entry_point("llm")
    .add_conditional_edges("llm", should_continue)
    .add_edge("tools", "llm")
    .compile(checkpointer=checkpointer)  # ← 传入 checkpointer，就这一行
)

# ========== 演示多轮对话 ==========
# thread_id 就是"会话 ID"，同一个 thread_id → 自动拼历史
# 对应 packages/api 里 messages 表的 session_id

config = {"configurable": {"thread_id": "demo-session-1"}}

def chat(user_input: str):
    print(f"\n用户: {user_input}")
    result = graph.invoke(
        {"messages": [HumanMessage(content=user_input)]},
        config=config,   # ← 每次都传同一个 config，框架自动续上历史
    )
    reply = result["messages"][-1].content
    print(f"AI:   {reply}")
    return reply

print("=" * 55)
print("演示：三轮对话，看 AI 是否记得前面说的话")
print("=" * 55)

# 第一轮：存一条笔记
chat("帮我把「深度学习比广度学习更重要」这个想法存成笔记，标签写 meta-learning")

# 第二轮：换话题
chat("我们公司 Q3 的重心是什么？")

# 第三轮：引用第一轮存的内容
# 如果 checkpointer 工作正常，AI 应该能回忆起第一轮存的笔记
chat("我刚才让你存的那条笔记，标题是什么？")

# ── 验证 ──
print("\n── 当前知识库 ──")
for n in KNOWN_NOTES:
    print(f"  [{n.get('tags','')}] {n['title']}: {n['content'][:50]}")

# ── 看一下 checkpointer 里存了什么 ──
print("\n── checkpoint 里的消息数 ──")
snapshot = graph.get_state(config)
print(f"  thread_id=demo-session-1 共 {len(snapshot.values['messages'])} 条消息")
print("  （三轮对话 × 平均 ~3 条/轮 = 约 9 条）")
