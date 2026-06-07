"""
04-sqlite-notes.py — SQLite 真数据库 + ReAct Loop
==================================================
学习目标：把 mock 数组换成真正的 SQLite，看到数据如何在磁盘上持久化

03 的内存数组一关程序就没了，04 的数据存在 .db 文件里。
"""
import os, json, sqlite3
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

# ========== 数据库初始化 ==========
DB_PATH = os.path.join(os.path.dirname(__file__), "notes.db")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row  # 让查询结果可以按列名取值

# 建表（只有一张 notes，你计划里的 6 张表留着后面加）
conn.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        tags TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
""")
conn.commit()

# 塞两条种子数据，让查询不是空的
conn.execute("DELETE FROM notes")  # 每次运行清掉旧数据，保持干净
conn.execute(
    "INSERT INTO notes (title, content, tags) VALUES (?, ?, ?)",
    ("B端优先级", "Q3 应该先做 B 端，收入能养活 C 端增长。2026-06-02 会议纪要", "产品,增长"),
)
conn.execute(
    "INSERT INTO notes (title, content, tags) VALUES (?, ?, ?)",
    ("用户留存问题", "用户留存下降可能和 onboarding 体验有关，需要 A/B 测试验证。2026-05-28 随手记", "产品,数据"),
)
conn.execute(
    "INSERT INTO notes (title, content, tags) VALUES (?, ?, ?)",
    ("技术债清单", "老登录模块耦合太深、没有 API 文档、测试覆盖率不到 30%。", "工程"),
)
conn.commit()
print(f"数据库就绪: {DB_PATH}（{conn.execute('SELECT COUNT(*) FROM notes').fetchone()[0]} 条笔记）")

# ========== 工具定义（和 03 一样） ==========
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "搜索笔记，用 LIKE 模糊匹配标题和正文。传一个关键词。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": "保存一条新笔记。调用前告诉用户存了什么。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "标题"},
                    "content": {"type": "string", "description": "正文"},
                    "tags": {"type": "string", "description": "逗号分隔的标签"},
                },
                "required": ["title", "content"],
            },
        },
    },
]

# ========== 工具执行器（跑真实 SQL） ==========
def execute_tool(tool_name, arguments):
    if tool_name == "search":
        query = arguments.get("query", "")
        # LIKE 模糊搜索，搜标题和正文
        rows = conn.execute(
            "SELECT id, title, content, tags, created_at FROM notes "
            "WHERE title LIKE ? OR content LIKE ? "
            "ORDER BY created_at DESC LIMIT 5",
            (f"%{query}%", f"%{query}%"),
        ).fetchall()
        results = [dict(r) for r in rows]
        return json.dumps(results, ensure_ascii=False)

    if tool_name == "save_note":
        conn.execute(
            "INSERT INTO notes (title, content, tags) VALUES (?, ?, ?)",
            (arguments.get("title", ""), arguments.get("content", ""), arguments.get("tags", "")),
        )
        conn.commit()
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return json.dumps({"status": "ok", "id": new_id}, ensure_ascii=False)

    return json.dumps({"error": f"未知工具: {tool_name}"})


# ========== ReAct Loop（和 03 一样） ==========
messages = [
    {"role": "system", "content": "你用中文回答。需要查资料时调 search，需要保存时调 save_note。"},
    {"role": "user", "content": "帮我查一下技术相关的笔记，总结一句，然后把我的新想法「今年重写老登录模块」存成笔记。"},
]

MAX_LOOP = 5

for i in range(MAX_LOOP):
    print(f"\n{'=' * 50}")
    print(f"第 {i + 1} 轮")

    response = client.chat.completions.create(
        model="deepseek-chat",
        max_tokens=500,
        messages=messages,
        tools=TOOLS,
    )

    msg = response.choices[0].message

    if msg.tool_calls:
        print(f"→ 调了 {len(msg.tool_calls)} 个工具：")
        messages.append(msg)

        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments)
            result = execute_tool(name, args)
            print(f"   {name}({json.dumps(args, ensure_ascii=False)})")
            print(f"   结果: {result[:120]}")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
        continue

    else:
        print(f"→ 最终回答：\n{msg.content}")

        # 验证：数据库真的被改了
        count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        print(f"\n当前数据库共 {count} 条笔记")

        rows = conn.execute("SELECT id, title FROM notes ORDER BY id").fetchall()
        for r in rows:
            print(f"  [{r['id']}] {r['title']}")
        break
else:
    print("⚠️ 达到 MAX_LOOP")

conn.close()