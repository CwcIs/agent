"""
10-full-stack.py — 完整原型：LangGraph + SqliteSaver + FastAPI SSE
===================================================================
学习目标：把前九个文件的所有技术点串成一个可运行的最小生产原型。

这个文件 ≈ packages/api 的骨架：
  06  FastAPI + SSE 端点
  07  LangGraph ReAct 图
  08  MemorySaver（多轮）
  09  SqliteSaver（持久化）
  全部合体 → 10

新增 vs 06：
  ✅ 多轮对话（同一 thread_id 自动续历史）
  ✅ 进程重启不丢历史（SqliteSaver）
  ✅ LangGraph 管循环，不再手写 for

新增 vs 09：
  ✅ 流式输出（SSE token 逐字推送）
  ✅ Web 页面，浏览器可直接用

核心难点：LangGraph 默认 .invoke() 是同步阻塞的。
  要 SSE 流式，需要用 .astream_events()（异步事件流）。
  每个 LLM token 会触发 "on_chat_model_stream" 事件，
  我们 yield 出去就成了 SSE token。

访问：
  http://localhost:3000        ← Web 页面
  curl "http://localhost:3000/chat/stream?q=你好&thread_id=abc"  ← 裸 SSE
"""
import os, json, sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from typing_extensions import TypedDict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

load_dotenv()

# ========== 业务 DB（notes）==========
NOTES_DB = Path(__file__).parent / "notes.db"
notes_conn = sqlite3.connect(str(NOTES_DB), check_same_thread=False)
notes_conn.row_factory = sqlite3.Row
notes_conn.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, content TEXT NOT NULL,
        tags TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
""")
# 种一条示例笔记（幂等）
if not notes_conn.execute("SELECT 1 FROM notes LIMIT 1").fetchone():
    notes_conn.execute("INSERT INTO notes (title, content, tags) VALUES (?,?,?)",
        ("B端优先级", "Q3 先做 B 端，收入养活 C 端增长。", "产品"))
    notes_conn.commit()

# ========== Checkpoint DB（LangGraph）==========
# 和 notes.db 分开，职责清晰
CHECKPOINT_DB = Path(__file__).parent / "checkpoint.db"

# ========== 工具 ==========
@tool
def search(query: str) -> str:
    """搜索笔记库"""
    rows = notes_conn.execute(
        "SELECT id, title, content, tags FROM notes WHERE title LIKE ? OR content LIKE ? LIMIT 5",
        (f"%{query}%", f"%{query}%"),
    ).fetchall()
    return json.dumps([dict(r) for r in rows], ensure_ascii=False)

@tool
def save_note(title: str, content: str, tags: str = "") -> str:
    """保存新笔记"""
    notes_conn.execute("INSERT INTO notes (title,content,tags) VALUES (?,?,?)", (title, content, tags))
    notes_conn.commit()
    return json.dumps({"status": "ok", "title": title}, ensure_ascii=False)

TOOLS = [search, save_note]

# ========== LLM ==========
llm = ChatOpenAI(
    model="deepseek-chat",
    openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
    openai_api_base="https://api.deepseek.com",
    max_tokens=500,
).bind_tools(TOOLS)

SYSTEM_PROMPT = "你用中文回答。需要查资料时调 search，用户要求保存时调 save_note。"

# ========== LangGraph ==========
class State(TypedDict):
    messages: Annotated[list, add_messages]

def call_llm(state: State) -> dict:
    msgs = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    return {"messages": [llm.invoke(msgs)]}

def should_continue(state: State) -> str:
    return "tools" if state["messages"][-1].tool_calls else END

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

# ========== FastAPI ==========
# astream_events() 是异步的，checkpointer 也必须用 AsyncSqliteSaver（不能用同步 SqliteSaver）
graph = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph
    async with AsyncSqliteSaver.from_conn_string(str(CHECKPOINT_DB)) as checkpointer:
        graph = build_graph(checkpointer)
        yield

app = FastAPI(title="My AI Platform — Full Stack Playground", lifespan=lifespan)

async def sse_stream(user_message: str, thread_id: str):
    """
    核心：用 astream_events() 把 LangGraph 的异步事件流转成 SSE。

    事件类型：
      on_chat_model_stream  → LLM 吐 token      → SSE "token"
      on_tool_start         → 工具开始执行       → SSE "tool_start"
      on_tool_end           → 工具执行完成       → SSE "tool"
      graph 跑完            → 最后 yield done    → SSE "done"
    """
    config = {"configurable": {"thread_id": thread_id}}
    input_state = {"messages": [HumanMessage(content=user_message)]}

    try:
        async for event in graph.astream_events(input_state, config=config, version="v2"):
            kind = event["event"]

            # LLM 逐 token 推送
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    yield {"event": "token", "data": chunk.content}

            # 工具调用开始
            elif kind == "on_tool_start":
                yield {
                    "event": "tool_start",
                    "data": json.dumps({"name": event["name"], "input": event["data"].get("input", {})}, ensure_ascii=False),
                }

            # 工具调用结束
            elif kind == "on_tool_end":
                output = event["data"].get("output", "")
                yield {
                    "event": "tool",
                    "data": json.dumps({"name": event["name"], "result": str(output)[:200]}, ensure_ascii=False),
                }

        yield {"event": "done", "data": json.dumps({"thread_id": thread_id})}

    except Exception as e:
        yield {"event": "error", "data": str(e)}


@app.get("/chat/stream")
async def chat_stream(q: str = "你好", thread_id: str = "default"):
    return EventSourceResponse(sse_stream(q, thread_id))


@app.get("/notes")
async def list_notes():
    rows = notes_conn.execute("SELECT * FROM notes ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


@app.get("/")
async def page():
    return HTMLResponse("""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>My AI Platform</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: system-ui; max-width: 760px; margin: 40px auto; padding: 0 20px; }
  h2 { margin-bottom: 4px; }
  .meta { color: #888; font-size: 13px; margin-bottom: 16px; }
  #chat { border: 1px solid #ddd; border-radius: 8px; padding: 16px;
          min-height: 320px; max-height: 520px; overflow-y: auto;
          margin-bottom: 12px; white-space: pre-wrap; line-height: 1.6; }
  .row { display: flex; gap: 8px; }
  #q { flex: 1; padding: 10px; font-size: 15px; border: 1px solid #ccc; border-radius: 6px; }
  #tid { width: 160px; padding: 10px; font-size: 14px; border: 1px solid #ccc; border-radius: 6px; color: #555; }
  .token { color: #1a1a1a; }
  .tool  { color: #6c757d; font-size: 12px; display: block; margin: 2px 0; }
  .tool_start { color: #0d6efd; font-size: 12px; display: block; }
  .done  { color: #198754; font-size: 12px; }
  .err   { color: #dc3545; font-size: 12px; }
  .sep   { color: #aaa; font-size: 11px; display: block; margin-top: 10px; }
</style></head><body>
<h2>My AI Platform — Playground</h2>
<p class="meta">10-full-stack · LangGraph + SqliteSaver + SSE · 多轮对话跨进程持久化</p>
<div id="chat">（输入消息，回车发送）</div>
<div class="row">
  <input id="tid" value="session-1" title="thread_id（会话ID）">
  <input id="q" placeholder="输入消息，回车发送..." autofocus>
</div>
<script>
const chat = document.getElementById('chat')
const input = document.getElementById('q')
const tidEl = document.getElementById('tid')
let es = null

function append(cls, text) {
  const el = document.createElement(cls === 'token' ? 'span' : 'div')
  el.className = cls; el.textContent = text
  chat.appendChild(el)
  chat.scrollTop = chat.scrollHeight
}

input.addEventListener('keydown', e => {
  if (e.key !== 'Enter' || !input.value.trim()) return
  const q = input.value.trim()
  const tid = tidEl.value.trim() || 'default'
  input.value = ''
  if (es) es.close()

  append('sep', `─── 发送 [${tid}]: ${q} ───`)

  es = new EventSource('/chat/stream?q=' + encodeURIComponent(q) + '&thread_id=' + encodeURIComponent(tid))
  es.addEventListener('token',      ev => append('token', ev.data))
  es.addEventListener('tool_start', ev => { const d = JSON.parse(ev.data); append('tool_start', '⚙ ' + d.name + '(' + JSON.stringify(d.input) + ')') })
  es.addEventListener('tool',       ev => { const d = JSON.parse(ev.data); append('tool', '↩ ' + d.name + ': ' + d.result) })
  es.addEventListener('done',       ev => { append('done', ' ✅'); es.close() })
  es.addEventListener('error',      ev => { append('err', '❌ ' + (ev.data || 'connection error')); es.close() })
})
</script>
</body></html>""")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
