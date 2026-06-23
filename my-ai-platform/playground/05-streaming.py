"""
05-streaming.py — 流式输出 + ReAct Loop
========================================
学习目标：看到 token 逐字到达，理解 SSE 的原理

04 是等模型全生成完再打印，05 是边生成边打字。
这是你计划 §5.3 里 SSE 通道的上游——先搞懂流本身。
"""
import os, json, sqlite3
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

# ========== 数据库 ==========
DB_PATH = os.path.join(os.path.dirname(__file__), "notes.db")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

conn.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        tags TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
""")
conn.execute("DELETE FROM notes")
conn.execute("INSERT INTO notes (title, content, tags) VALUES (?,?,?)",
    ("B端优先级", "Q3 先做 B 端，收入养活 C 端增长。", "产品,增长"))
conn.execute("INSERT INTO notes (title, content, tags) VALUES (?,?,?)",
    ("技术债清单", "老登录模块耦合太深，测试覆盖率不到 30%。", "工程"))
conn.commit()

# ========== 工具 ==========
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "搜索笔记，传关键词",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
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


def execute_tool(tool_name, arguments):
    if tool_name == "search":
        q = arguments.get("query", "")
        rows = conn.execute(
            "SELECT id, title, content, tags FROM notes WHERE title LIKE ? OR content LIKE ? LIMIT 5",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)
    if tool_name == "save_note":
        conn.execute("INSERT INTO notes (title, content, tags) VALUES (?,?,?)",
            (arguments.get("title", ""), arguments.get("content", ""), arguments.get("tags", "")))
        conn.commit()
        return json.dumps({"status": "ok"})
    return json.dumps({"error": f"未知工具: {tool_name}"})


# ========== 流式 ReAct Loop ==========
messages = [
    {"role": "system", "content": "你用中文回答。需要时调 search 或 save_note。"},
    {"role": "user", "content": "查一下技术债相关的笔记，总结一句。"},
]

MAX_LOOP = 5

for i in range(MAX_LOOP):
    print(f"\n{'=' * 50}")
    print(f"第 {i + 1} 轮")

    # ★ 关键改动：加了 stream=True
    stream = client.chat.completions.create(
        model="deepseek-chat",
        max_tokens=500,
        messages=messages,
        tools=TOOLS,
        stream=True,  # ← 就这一行
    )

    # ★ 因为流是分块到达的，不能直接 .choices[0].message
    #    要自己把所有块拼起来
    collected = {
        "content": "",
        "tool_calls": [],  # tool call 也是分块到达的
    }

    print("模型输出: ", end="", flush=True)
    for chunk in stream:
        delta = chunk.choices[0].delta

        # ── 文本块：直接打印，像打字机一样 ──
        if delta.content:
            print(delta.content, end="", flush=True)
            collected["content"] += delta.content

        # ── tool_calls 块：碎片拼起来 ──
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                # tool_calls 的 index 告诉你是第几个工具
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

    print()  # 换行

    # ── 判断：有 tool call 还是直接回答 ──
    if collected["tool_calls"] and collected["tool_calls"][0]["function"]["name"]:
        print(f"→ 模型调了 {len(collected['tool_calls'])} 个工具：")

        # 构造和 non-stream 格式一样的 assistant 消息（plain dict）
        tool_calls_for_msg = []
        for tc in collected["tool_calls"]:
            tool_calls_for_msg.append({
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                },
            })
        msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls_for_msg,
        }
        messages.append(msg)

        for tc in tool_calls_for_msg:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])
            result = execute_tool(name, args)
            print(f"   {name}({json.dumps(args, ensure_ascii=False)})")
            print(f"   结果: {result[:120]}")

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })
        continue

    else:
        # 直接回答，结束
        print(f"\n→ 完成，共 {i + 1} 轮")
        break
else:
    print("⚠️ MAX_LOOP")

conn.close()
