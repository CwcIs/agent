import os, json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("DEEPSEEK_API_KEY")

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
)

# ========== 新增：模拟知识库 ==========
KNOWN_NOTES = [
    {"title": "B端优先级", "content": "Q3 应该先做 B 端，收入能养活 C 端增长。2026-06-02 会议纪要"},
    {"title": "用户留存问题", "content": "用户留存下降可能和 onboarding 体验有关，需要 A/B 测试验证。2026-05-28 随手记"},
    {"title": "技术债清单", "content": "老登录模块耦合太深、没有 API 文档、测试覆盖率不到 30%。"},
]
# ======================================

# ========== 新增：工具定义 ==========

TOOLS = [
    {
        "type": "function",
        "function":{
            "name": "search",
            "description": "在知识库中搜索相关内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                },
                "required": ["query"],
            },
        }
    }
]

# ====================================

# ========== 新增：真正执行工具的函数 ==========
def execute_tool(tool_name, arguments):
    if tool_name == "search":
        query = arguments.get("query", "") # 新增：获取参数
        results = [note for note in KNOWN_NOTES if query in note["title"] or query in note["content"]]
        return json.dumps(results, ensure_ascii=False) # 返回 JSON 字符串
    else:
        return "工具未找到"
    
  # ===============================================

# ========== 核心：带 tool 的消息循环 ==========
messages = [
    {"role": "system", "content": "你用中文回答。当需要查资料时，先调 search 工具。"},
    {"role": "user", "content": "我之前对 B 端有什么想法？帮我查一下。"},
]

# 第一轮：发消息 + tool 定义
response = client.chat.completions.create(
    model="deepseek-chat",
    max_tokens=500,
    messages=messages,
    tools=TOOLS,                      # ← 告诉模型有哪些工具可用
)

msg = response.choices[0].message
print("=" * 50)
print("第一轮 — 模型的选择：")

if msg.tool_calls:                    # ← 模型选择了调工具，不是直接说话
    print(f"模型要求调用工具！次数: {len(msg.tool_calls)}")

    # 把这轮 assistant 的 tool_calls 记入对话历史
    messages.append(msg)

    for tc in msg.tool_calls:
        name = tc.function.name
        args = json.loads(tc.function.arguments)
        print(f"  工具名: {name}")
        print(f"  参数  : {args}")

        # 真正执行工具
        result = execute_tool(name, args)
        print(f"  结果  : {result[:80]}...")

        # 把执行结果作为 tool 消息追加到对话历史
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": result,
        })

    print("=" * 50)
    print("第二轮 — 把结果喂回模型，拿最终回复：")

    # 第二轮：把工具结果喂回去，让模型生成最终回答
    response2 = client.chat.completions.create(
        model="deepseek-chat",
        max_tokens=500,
        messages=messages,
    )
    print(response2.choices[0].message.content)

else:
    # 模型认为不需要工具，直接回答
    print("模型没调工具，直接回答：")
    print(msg.content)

print("=" * 50)

# ======================================