#!/usr/bin/env python3
"""
黄金集 eval runner
用法：python evals/run.py
需要后端在 localhost:8000 跑着，或设置 BASE_URL 环境变量。
"""

import json
import os
import sys
import asyncio
import sqlite3
from pathlib import Path

# 加载项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "my-ai-platform/packages/api"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "my-ai-platform/.env")

from langchain_core.messages import HumanMessage, SystemMessage
from src.agent.providers.deepseek import make_deepseek
from src.tools import make_tools
from src.db.schema import get_conn, init_db

GOLDEN_PATH = Path(__file__).parent / "golden.jsonl"


def load_cases():
    with open(GOLDEN_PATH) as f:
        return [json.loads(l) for l in f if l.strip()]


async def run_case(case: dict, llm) -> dict:
    user_input = case["input"]
    expect_tool = case.get("expect_tool")

    try:
        msgs = [
            SystemMessage(content="""你是用户的个人知识助手，用中文回答。
你有三个工具：
- get_notes_summary：获取笔记库聚合统计（总数、近7天新增、主要话题分布）
- search_notes：按关键词检索笔记全文，返回匹配列表
- synthesize_notes：跨笔记综合，生成关于某话题的洞察分析
- save_note：把重要内容存成笔记

使用规则：
1. 用户问"有什么笔记"、"笔记概况"、"笔记库里有什么" → 调 get_notes_summary
2. 用户问"有没有记过 X"、"找找 X"、"搜一下 X"、"X 相关的笔记" → 调 search_notes
3. 用户问"我对 X 有哪些理解"、"总结我关于 X 的想法"、"X 方面我记了什么" → 调 synthesize_notes
4. search_notes 返回空时 → 告知没找到，询问是否换词或保存新笔记
5. 用户要求保存时 → 调 save_note
6. 纯知识问答（"X 是什么"、"怎么理解 X"）→ 直接回答，不调工具"""),
            HumanMessage(content=user_input),
        ]
        response = await llm.ainvoke(msgs)
        tool_calls = getattr(response, "tool_calls", []) or []
        actual_tool = tool_calls[0]["name"] if tool_calls else None

        passed = actual_tool == expect_tool
        return {
            "id": case["id"],
            "passed": passed,
            "expect": expect_tool,
            "actual": actual_tool,
            "description": case["description"],
            "error": None,
        }
    except Exception as e:
        return {
            "id": case["id"],
            "passed": False,
            "expect": expect_tool,
            "actual": None,
            "description": case["description"],
            "error": str(e),
        }


async def main():
    cases = load_cases()
    print(f"加载 {len(cases)} 条黄金案例\n")

    # 用真实 db 初始化工具（eval 只测工具调用决策，不真正执行）
    db_path = Path(__file__).parent.parent / "my-ai-platform/packages/api/data/notes.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)

    tools = make_tools(conn)
    llm = make_deepseek(tools)

    results = await asyncio.gather(*[run_case(c, llm) for c in cases])

    # 打印结果
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    json_errors = sum(1 for r in results if r["error"])

    print(f"{'ID':<12} {'结果':<6} {'期望工具':<22} {'实际工具':<22} 描述")
    print("-" * 90)
    for r in results:
        icon = "✅" if r["passed"] else "❌"
        expect = r["expect"] or "(无)"
        actual = r["actual"] or "(无)"
        if r["error"]:
            actual = f"ERROR: {r['error'][:30]}"
        print(f"{r['id']:<12} {icon}     {expect:<22} {actual:<22} {r['description']}")

    print("-" * 90)
    pass_rate = passed / total * 100
    error_rate = json_errors / total * 100
    print(f"\n通过率：{passed}/{total} = {pass_rate:.0f}%  (验收线 ≥ 80%)")
    print(f"错误率：{json_errors}/{total} = {error_rate:.0f}%  (验收线 < 5%)")

    if pass_rate >= 80 and error_rate < 5:
        print("\n✅ PASS — 黄金集验收通过")
        sys.exit(0)
    else:
        print("\n❌ FAIL — 未达验收标准")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
