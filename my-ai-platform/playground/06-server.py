"""
06-server.py — FastAPI + SSE 把 ReAct Loop 推到浏览器
======================================================
学习目标：把 05 的终端打印变成 HTTP 流式接口

05: print() → 只能自己在终端看
06: yield → 任何浏览器都能连过来看

访问 http://localhost:3000 打开简陋 Web 页面
或在终端 curl http://localhost:3000/chat/stream 看 SSE 裸流
"""
import os, json, sqlite3
from openai import OpenAI
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

load_dotenv()

# ========== 数据库 ==========
DB_PATH = os.path.join(os.path.dirname(__file__), "notes.db")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
conn.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, content TEXT NOT NULL,
        tags TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
""")
conn.execute("DELETE FROM notes")
conn.execute("INSERT INTO notes (title, content, tags) VALUES (?,?,?)",
    ("B端优先级", "Q3 先做 B 端，收入养活 C 端增长。", "产品,增长"))
conn.execute("INSERT INTO notes (title, content, tags) VALUES (?,?,?)",
    ("技术债清单", "老登录模块耦合太深，测试覆盖率不到30%。", "工程"))
conn.commit()

# ========== 工具（和 05 一样） ==========
TOOLS = [
    {
        "type": "function", "function": {
            "name": "search",
            "description": "搜索笔记",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function", "function": {
            "name": "save_note",
            "description": "保存笔记",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "tags": {"type": "string"},
                },
                "required": ["title", "content"],
            },
        },
    },
]


def execute_tool(name, args):
    if name == "search":
        q = args.get("query", "")
        rows = conn.execute(
            "SELECT id, title, content, tags FROM notes WHERE title LIKE ? OR content LIKE ? LIMIT 5",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)
    if name == "save_note":
        conn.execute("INSERT INTO notes (title, content, tags) VALUES (?,?,?)",
            (args.get("title", ""), args.get("content", ""), args.get("tags", "")))
        conn.commit()
        return json.dumps({"status": "ok"})
    return json.dumps({"error": f"未知工具: {name}"})


# ========== FastAPI 应用 ==========
app = FastAPI(title="My AI Platform — Playground")

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)


async def run_react_loop(user_message: str):
    """
    流式 ReAct Loop，用 yield 往外吐 SSE 事件。
    对比 05 里的 print()——这里的 yield 就是"推给浏览器"。
    """
    messages = [
        {"role": "system", "content": "你用中文回答。需要时调 search 或 save_note。"},
        {"role": "user", "content": user_message},
    ]
    MAX_LOOP = 5

    for i in range(MAX_LOOP):
        yield {"event": "status", "data": json.dumps({"round": i + 1})}

        stream = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=500,
            messages=messages,
            tools=TOOLS,
            stream=True,
        )

        collected = {"content": "", "tool_calls": []}

        for chunk in stream:
            delta = chunk.choices[0].delta

            if delta.content:
                collected["content"] += delta.content
                # ★ 这就是 SSE：每拿到一个 token，立刻推给浏览器
                yield {"event": "token", "data": delta.content}

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    while len(collected["tool_calls"]) <= idx:
                        collected["tool_calls"].append({"id": "", "function": {"name": "", "arguments": ""}})
                    if tc_delta.id:
                        collected["tool_calls"][idx]["id"] += tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            collected["tool_calls"][idx]["function"]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            collected["tool_calls"][idx]["function"]["arguments"] += tc_delta.function.arguments

        # ── tool call 分支 ──
        if collected["tool_calls"] and collected["tool_calls"][0]["function"]["name"]:
            tool_calls_for_msg = []
            for tc in collected["tool_calls"]:
                tool_calls_for_msg.append({
                    "id": tc["id"], "type": "function",
                    "function": {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]},
                })
            messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls_for_msg})

            for tc in tool_calls_for_msg:
                name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                result = execute_tool(name, args)
                yield {"event": "tool", "data": json.dumps({"name": name, "args": args, "result": result[:200]}, ensure_ascii=False)}
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            continue

        else:
            yield {"event": "done", "data": json.dumps({"rounds": i + 1})}
            break
    else:
        yield {"event": "error", "data": "MAX_LOOP"}


# ========== 路由 ==========

@app.get("/chat/stream")
async def chat_stream(q: str = "你好，介绍一下你自己"):
    """SSE 端点：浏览器 EventSource 直接连这个"""
    return EventSourceResponse(run_react_loop(q))


@app.get("/")
async def page():
    """一个简陋 Web 页面，让你在浏览器里试"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><title>My AI Platform - Playground</title>
    <style>
      body { font-family: system-ui; max-width: 700px; margin: 40px auto; padding: 0 20px; }
      #chat { border: 1px solid #ddd; border-radius: 8px; padding: 16px; min-height: 300px; margin-bottom: 12px; white-space: pre-wrap; }
      input { width: 100%; padding: 10px; font-size: 16px; border: 1px solid #ccc; border-radius: 6px; }
      .token { color: #333; } .tool { color: #888; font-size: 13px; } .status { color: #aaa; font-size: 12px; }
    </style></head><body>
    <h2>🧪 My AI Platform — Playground</h2>
    <div id="chat"></div>
    <input id="q" placeholder="输入消息，回车发送..." autofocus>
    <script>
    const chat = document.getElementById('chat'), input = document.getElementById('q')
    input.addEventListener('keydown', e => {
      if (e.key !== 'Enter' || !input.value.trim()) return
      const q = input.value.trim(); input.value = ''; chat.innerHTML = ''
      const es = new EventSource('/chat/stream?q=' + encodeURIComponent(q))
      es.addEventListener('token', e => { const s = document.createElement('span'); s.className='token'; s.textContent = e.data; chat.appendChild(s) })
      es.addEventListener('tool', e => { const d = document.createElement('div'); d.className='tool'; d.textContent = '🔧 ' + e.data; chat.appendChild(d) })
      es.addEventListener('status', e => { const d = document.createElement('div'); d.className='status'; d.textContent = '--- 第 ' + JSON.parse(e.data).round + ' 轮 ---'; chat.appendChild(d) })
      es.addEventListener('done', e => { es.close(); const d = document.createElement('div'); d.className='status'; d.textContent = '✅ 完成'; chat.appendChild(d) })
      es.addEventListener('error', e => { es.close() })
    })
    </script>
    </body></html>
    """)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)