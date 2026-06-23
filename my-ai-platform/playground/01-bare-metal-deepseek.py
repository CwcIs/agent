import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
)

response = client.chat.completions.create(
    model="deepseek-chat",
    max_tokens=500,
    messages=[
        {"role": "system", "content": "你用中文回答，简洁直接。"},
        {"role": "user", "content": "你好，请用一句话解释什么是 API。"},
    ]
)

print("=" * 50)
print("DeepSeek 回复：")
print(response.choices[0].message.content)
print("=" * 50)
print(f"输入 token: {response.usage.prompt_tokens}")
print(f"输出 token: {response.usage.completion_tokens}")

