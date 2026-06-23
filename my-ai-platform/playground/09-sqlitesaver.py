"""
09-sqlitesaver.py — 持久化 checkpoint（SqliteSaver）
====================================================
学习目标：把 08 的 MemorySaver 换成 SqliteSaver，进程重启后对话历史还在。

运行方式（两步演示持久化）：
  第一次：python playground/09-sqlitesaver.py --turn 1
  第二次：python playground/09-sqlitesaver.py --turn 2
  两次是独立进程，但 AI 在第二次仍然记得第一次说的话。

08 MemorySaver vs 09 SqliteSaver：
  MemorySaver  → 存在 Python 进程内存，kill 掉就没了
  SqliteSaver  → 存在 checkpoint.db，进程重启照样有

这对 Phase 1 的意义：
  packages/api 用 uvicorn 跑，每次重启（改代码、崩溃恢复）
  都不能丢用户对话历史。SqliteSaver 解决这个问题。
  存 checkpoint 的 DB 可以和业务 DB（notes.db）是同一个文件，
  也可以分开——Phase 1 建议分开，职责清晰。

SqliteSaver 存的是什么？
  LangGraph 的 checkpoint 格式，不是你的 notes 表。
  它存：每个 thread_id 的完整 messages 列表（序列化成 blob）。
  你自己的业务数据（notes）还是存 notes 表，两张表不冲突。

安装依赖（如果还没装）：
  pip install langgraph-checkpoint-sqlite
"""
import os, json, sys, argparse
from typing import Annotated
from pathlib import Path
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite import SqliteSaver   # ← 换这一行
from typing_extensions import TypedDict

load_dotenv()

# checkpoint DB 放在 playground 目录旁边，方便演示后手动删除
DB_PATH = Path(__file__).parent / "checkpoint.db"

# ========== 工具 + 知识库 ==========
KNOWN_NOTES = [
    {"title": "B端优先级", "content": "Q3 应该先做 B 端，收入能养活 C 端增长。"},
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
    return "tools" if state["messages"][-1].tool_calls else END

# ========== 构图（SqliteSaver 需要 with 上下文管理器）==========
# SqliteSaver 不像 MemorySaver 可以直接实例化，
# 它需要持有一个数据库连接，所以用 with 块管理生命周期。

def build_graph(checkpointer):
    return (
        StateGraph(State)
        .add_node("llm", call_llm)
        .add_node("tools", ToolNode(TOOLS))
        .set_entry_point("llm")
        .add_conditional_edges("llm", should_continue)
        .add_edge("tools", "llm")
        .compile(checkpointer=checkpointer)
    )

# ========== 演示逻辑 ==========
THREAD_ID = "persistent-session-1"  # 两次运行用同一个 thread_id

def run_turn_1(graph):
    """第一次运行：存一条笔记"""
    config = {"configurable": {"thread_id": THREAD_ID}}
    print("=" * 55)
    print("第一次运行（turn 1）")
    print("=" * 55)

    user_msg = "帮我把「系统思考比局部优化更重要」存成笔记，标签写 thinking"
    print(f"用户: {user_msg}")
    result = graph.invoke({"messages": [HumanMessage(content=user_msg)]}, config=config)
    print(f"AI:   {result['messages'][-1].content}")

    snapshot = graph.get_state(config)
    print(f"\n✅ checkpoint 已写入 {DB_PATH}")
    print(f"   thread_id={THREAD_ID} 共 {len(snapshot.values['messages'])} 条消息")
    print("\n现在重新运行，加参数 --turn 2：")
    print("  python playground/09-sqlitesaver.py --turn 2")

def run_turn_2(graph):
    """第二次运行（新进程）：验证记忆还在"""
    config = {"configurable": {"thread_id": THREAD_ID}}
    print("=" * 55)
    print("第二次运行（turn 2）— 新进程，验证持久化")
    print("=" * 55)

    # 先看 checkpoint 里有多少消息（应该是 turn 1 留下的）
    snapshot = graph.get_state(config)
    if not snapshot.values:
        print("❌ checkpoint 里没有历史记录，请先运行 --turn 1")
        return

    print(f"从 checkpoint 恢复：{len(snapshot.values['messages'])} 条历史消息")

    user_msg = "我刚才让你存的那条笔记，标题和标签是什么？"
    print(f"用户: {user_msg}")
    result = graph.invoke({"messages": [HumanMessage(content=user_msg)]}, config=config)
    print(f"AI:   {result['messages'][-1].content}")

    snapshot2 = graph.get_state(config)
    print(f"\n✅ 两轮合计 {len(snapshot2.values['messages'])} 条消息")
    print(f"   （turn 1 的历史跨进程保留下来了）")

# ========== 入口 ==========
parser = argparse.ArgumentParser()
parser.add_argument("--turn", type=int, choices=[1, 2], default=1,
                    help="1=第一次运行存笔记，2=第二次运行验证记忆")
parser.add_argument("--reset", action="store_true",
                    help="删除 checkpoint.db，重新开始")
args = parser.parse_args()

if args.reset and DB_PATH.exists():
    DB_PATH.unlink()
    print(f"已删除 {DB_PATH}，重新开始\n")

# SqliteSaver 用 with 管理连接生命周期
with SqliteSaver.from_conn_string(str(DB_PATH)) as checkpointer:
    graph = build_graph(checkpointer)
    if args.turn == 1:
        run_turn_1(graph)
    else:
        run_turn_2(graph)
