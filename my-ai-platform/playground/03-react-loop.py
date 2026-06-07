"""
03-react-loop.py — ReAct Tool Loop
=================================
学习目标：看到模型如何在"思考→调工具→拿结果→再思考"之间自动循环

02 是手写两轮，03 包成 for 循环。
这就是你计划 §8.6 里 runReActLoop() 的内核，不含任何框架。
"""
import os, json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

# ========== 模拟知识库 ==========
KNOWN_NOTES = [
    {"title": "B端优先级", "content": "Q3 应该先做 B 端，收入能养活 C 端增长。2026-06-02 会议纪要"},
    {"title": "用户留存问题", "content": "用户留存下降可能和 onboarding 体验有关，需要 A/B 测试验证。2026-05-28 随手记"},
    {"title": "技术债清单", "content": "老登录模块耦合太深、没有 API 文档、测试覆盖率不到 30%。"},
]

# ========== 工具定义 ==========
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "搜索知识库中的笔记，传一个关键词，返回匹配的笔记列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，例如 'B端'、'留存'",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": "保存一条新笔记到知识库。调用前必须先告诉用户你要存什么。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "笔记标题"},
                    "content": {"type": "string", "description": "笔记正文"},
                    "tags": {"type": "string", "description": "标签，逗号分隔，例如 '产品,增长'"},
                },
                "required": ["title", "content"],
            },
        },
    },
]

# ========== 工具执行器 ==========
def execute_tool(tool_name, arguments):
    if tool_name == "search":
        query = arguments.get("query", "")
        results = [n for n in KNOWN_NOTES if query in n["title"] or query in n["content"]]
        return json.dumps(results, ensure_ascii=False)

    if tool_name == "save_note":
        note = {
            "title": arguments.get("title", ""),
            "content": arguments.get("content", ""),
            "tags": arguments.get("tags", ""),
        }
        KNOWN_NOTES.append(note)  # 真正写入（内存中）
        return json.dumps({"status": "ok", "note": note}, ensure_ascii=False)

    return json.dumps({"error": f"未知工具: {tool_name}"})


# ========== ReAct Loop ==========
messages = [
    {"role": "system", "content": "你用中文回答。需要查资料时调 search，用户要求保存时调 save_note。"},
    {"role": "user", "content": "帮我查一下之前关于 B 端的笔记，然后总结一句，最后把我的这句话「做 B 端是今年的关键决策」存成笔记。"},
]

MAX_LOOP = 5  # 安全上限

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
        # ----- 模型要调工具 -----
        print(f"→ 调了 {len(msg.tool_calls)} 个工具：")
        messages.append(msg)

        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments)
            result = execute_tool(name, args)
            print(f"   {name}({json.dumps(args, ensure_ascii=False)})")
            print(f"   结果: {result[:100]}")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
        # 回到 for 顶部，继续下一轮
        continue

    else:
        # ----- 模型直接回答，结束 -----
        print(f"→ 最终回答：\n{msg.content}")
        print(f"\n{'=' * 50}")
        print(f"总轮数: {i + 1}")

        # 看看知识库有没有被改过
        if any(n for n in KNOWN_NOTES if "B端" in n.get("tags", "")):
            print("✅ 新笔记已存入知识库！")
        break
else:
    print("⚠️ 达到 MAX_LOOP 上限，模型还没停")