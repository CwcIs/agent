"""
07-langgraph.py — 用 LangGraph 重写 03 的 ReAct Loop
======================================================
学习目标：理解 LangGraph 把 03 里的 for 循环"图化"之后，你得到了什么、丢了什么。

03 手写版：
  for i in range(MAX_LOOP):
      response = llm(messages)
      if tool_calls: execute → continue
      else: break

07 LangGraph 版：
  nodes  = { "llm": call_llm,  "tools": run_tools }
  edges  = { "llm" → 有 tool_call? → "tools" : END }
           { "tools" → "llm" }
  graph.invoke(state)   ← 框架自己跑循环

对比表
──────────────────────────────────────────────────────────
              03 手写                07 LangGraph
──────────────────────────────────────────────────────────
循环控制      手写 for + break      框架负责（conditional_edge）
状态管理      你的 messages 列表    TypedDict State（自动 append）
工具分发      if name == "search"   ToolNode（自动路由）
中断/恢复     不支持                checkpointer → 可暂停续跑
可视化        无                    graph.get_graph().draw_ascii()
──────────────────────────────────────────────────────────

什么时候值得用 LangGraph？
  - 需要暂停等人工审批（Human-in-the-loop）
  - 需要跨进程 / 跨请求恢复状态（checkpointer）
  - 多 Agent 协作，节点之间路由复杂
  Phase 1 的 ReAct loop 其实手写版更透明，
  但 LangGraph 是 packages/api 里用的框架，所以要学会读它。
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
from typing_extensions import TypedDict

load_dotenv()

# ========== 模拟知识库（和 03 一样）==========
KNOWN_NOTES = [
    {"title": "B端优先级", "content": "Q3 应该先做 B 端，收入能养活 C 端增长。2026-06-02 会议纪要"},
    {"title": "用户留存问题", "content": "用户留存下降可能和 onboarding 体验有关，需要 A/B 测试验证。"},
    {"title": "技术债清单", "content": "老登录模块耦合太深、没有 API 文档、测试覆盖率不到 30%。"},
]

# ========== 工具定义（@tool 装饰器，LangChain 风格）==========
# 03 里工具是 dict，这里变成函数 + 装饰器。
# ToolNode 会自动根据函数名分发调用，不需要 if name == "search"。

@tool
def search(query: str) -> str:
    """搜索知识库中的笔记，传一个关键词，返回匹配的笔记列表"""
    results = [n for n in KNOWN_NOTES if query in n["title"] or query in n["content"]]
    return json.dumps(results, ensure_ascii=False)

@tool
def save_note(title: str, content: str, tags: str = "") -> str:
    """保存一条新笔记到知识库"""
    note = {"title": title, "content": content, "tags": tags}
    KNOWN_NOTES.append(note)
    return json.dumps({"status": "ok", "note": note}, ensure_ascii=False)

TOOLS = [search, save_note]

# ========== LLM ==========
llm = ChatOpenAI(
    model="deepseek-chat",
    openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
    openai_api_base="https://api.deepseek.com",
    max_tokens=500,
).bind_tools(TOOLS)  # ← 把工具绑到 LLM，相当于 03 里传 tools=TOOLS

# ========== State ==========
# LangGraph 的状态是 TypedDict。
# Annotated[list, add_messages] 告诉框架：每轮 messages 是追加，不是覆盖。
# 对比 03：你手动 messages.append(msg)，这里框架自动做。

class State(TypedDict):
    messages: Annotated[list, add_messages]

# ========== Nodes ==========
SYSTEM_PROMPT = "你用中文回答。需要查资料时调 search，用户要求保存时调 save_note。"

def call_llm(state: State) -> dict:
    """LLM 节点：拿当前 messages → 调 LLM → 返回新消息追加到 state"""
    # 注意：第一次进来 state["messages"] 只有 HumanMessage，
    # 后续轮次会带上 ToolMessage（工具结果）。
    # SystemMessage 每次都加在最前面（简单做法，Phase 1 够用）。
    msgs = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm.invoke(msgs)
    return {"messages": [response]}

# ToolNode 是 LangGraph 内置节点，自动：
#   1. 解析 AIMessage 里的 tool_calls
#   2. 按函数名找到对应 @tool 函数并执行
#   3. 把结果包成 ToolMessage 追加到 state
# 对比 03：这 3 步全是你手写的。
tool_node = ToolNode(TOOLS)

# ========== 路由函数 ==========
# 替代 03 里的 if msg.tool_calls: continue / else: break
def should_continue(state: State) -> str:
    last = state["messages"][-1]
    if last.tool_calls:
        return "tools"
    return END

# ========== 构图 ==========
graph = (
    StateGraph(State)
    .add_node("llm", call_llm)
    .add_node("tools", tool_node)
    .set_entry_point("llm")
    .add_conditional_edges("llm", should_continue)  # llm → tools or END
    .add_edge("tools", "llm")                        # tools → llm（循环）
    .compile()
)

# ========== 可视化（选看）==========
print("图结构：")
print(graph.get_graph().draw_ascii())
print()

# ========== 运行 ==========
print("=" * 50)
print("问题：帮我查一下之前关于 B 端的笔记，然后总结一句，最后把「做 B 端是今年的关键决策」存成笔记。")
print("=" * 50)

result = graph.invoke({
    "messages": [HumanMessage(content="帮我查一下之前关于 B 端的笔记，然后总结一句，最后把「做 B 端是今年的关键决策」存成笔记。")]
})

# 打印每一轮消息，方便和 03 的 print 输出对比
print("\n── 完整消息历史 ──")
for i, msg in enumerate(result["messages"]):
    role = msg.__class__.__name__
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        print(f"[{i}] {role}: 调工具 → {[tc['name'] for tc in msg.tool_calls]}")
    elif hasattr(msg, "name"):  # ToolMessage
        print(f"[{i}] {role}({msg.name}): {msg.content[:80]}")
    else:
        content_preview = (msg.content or "")[:120]
        print(f"[{i}] {role}: {content_preview}")

print("\n── 最终回答 ──")
print(result["messages"][-1].content)

# 验证笔记有没有存进去
saved = [n for n in KNOWN_NOTES if "关键决策" in n.get("content", "")]
print(f"\n{'✅ 新笔记已存入！' if saved else '❌ 笔记未存入'}")
