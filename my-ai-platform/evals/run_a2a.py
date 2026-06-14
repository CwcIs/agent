#!/usr/bin/env python3
"""
A2A 端到端 eval runner — 测试 knowledge → review 链
用法：python evals/run_a2a.py
需要 .env 中有 DEEPSEEK_API_KEY。

评测指标：
  - agents_correct  — 链路上出现的 Agent 是否与预期一致
  - depth_ok        — 链路深度是否达到预期
  - challenge_found — ReviewAgent 是否实际输出了挑战内容
  - chain_completed — 链路是否正常终止（无异常中断）
  - no_loop         — 未触发 loop_detected

验收线：所有指标 ≥ 80%（5 条中至少 4 条通过）
"""

import json
import os
import sys
import asyncio
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "api"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from src.agent.registry import init_registry
from src.agent.router import route_serial
from src.db.schema import init_db

GOLDEN_PATH = Path(__file__).parent / "golden_a2a.jsonl"


def load_cases():
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def has_challenge_content(text: str) -> bool:
    """检查 ReviewAgent 输出中是否包含实际的挑战内容（不是纯附和）。"""
    # 挑战信号词
    challenge_markers = [
        "漏洞", "假设", "反例", "矛盾", "不足", "局限",
        "问题在于", "但是", "然而", "另一方面", "值得商榷",
        "不一定", "未必", "缺少", "忽略", "忽视",
        "fallacy", "however", "but", "weakness", "gap",
    ]
    return any(marker in text for marker in challenge_markers)


async def run_a2a_case(case: dict, conn: sqlite3.Connection) -> dict:
    """运行单条 A2A 评测：通过 router 执行完整链路。"""
    session_id = f"eval-a2a-{case['id']}"

    try:
        events = []
        full_texts: dict[str, str] = {}  # agent_id → accumulated text

        async for event in route_serial(case["input"], session_id, conn):
            events.append(event)

            # 收集每个 agent 的完整输出
            if event["type"] == "token":
                agent = event.get("agentId", "unknown")
                full_texts[agent] = full_texts.get(agent, "") + event["delta"]

        # ── 分析事件流 ──
        agent_switches = [e for e in events if e["type"] == "agent_switch"]
        agents_seen = [e["agentId"] for e in agent_switches]
        # 第一个 agent 没有 agent_switch 事件，需从第一个 token 推断
        first_tokens = [e for e in events if e["type"] == "token"]
        if first_tokens and "knowledge" not in agents_seen:
            agents_seen.insert(0, "knowledge")

        depth = len(agent_switches) + 1  # 第一跳 + 切换次数
        has_done = any(e["type"] == "done" for e in events)
        verdicts = [e for e in events if e["type"] == "verdict"]
        warnings = [e for e in events if e["type"] == "warning"]
        errors = [e for e in events if e["type"] == "error"]

        # 检查 review agent 是否输出了挑战内容
        review_text = full_texts.get("review", "")
        challenge_found = has_challenge_content(review_text)

        # 检查是否被 loop_detected 终止
        loop_triggered = any(
            v.get("reason") == "loop_detected" for v in verdicts
        )

        # ── 评分 ──
        expected = set(case["expect_agents"])
        actual = set(agents_seen)
        agents_correct = expected.issubset(actual)  # 预期 agent 至少都出现

        depth_ok = depth >= case.get("expect_min_depth", 2)
        challenge_ok = not case.get("expect_challenge", True) or challenge_found
        chain_ok = has_done and not errors and not loop_triggered

        all_ok = agents_correct and depth_ok and challenge_ok and chain_ok

        return {
            "id": case["id"],
            "passed": all_ok,
            "agents_correct": agents_correct,
            "depth_ok": depth_ok,
            "challenge_found": challenge_ok,
            "chain_completed": chain_ok,
            "no_loop": not loop_triggered,
            "actual_agents": agents_seen,
            "actual_depth": depth,
            "verdict_reasons": [v.get("reason") for v in verdicts],
            "warnings": [w.get("message", "")[:80] for w in warnings],
            "errors": [e.get("message", "")[:80] for e in errors],
            "error": None,
        }
    except Exception as e:
        return {
            "id": case["id"],
            "passed": False,
            "agents_correct": False,
            "depth_ok": False,
            "challenge_found": False,
            "chain_completed": False,
            "no_loop": True,
            "actual_agents": [],
            "actual_depth": 0,
            "verdict_reasons": [],
            "warnings": [],
            "errors": [],
            "error": str(e),
        }


async def main():
    cases = load_cases()
    print(f"加载 {len(cases)} 条 A2A 黄金案例\n")

    # 初始化 Agent 注册表（内存数据库）
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    init_registry(conn)

    print("运行 A2A 链路评测（每条需要 1-2 次 LLM 调用，请耐心等待）...\n")

    results = []
    for case in cases:
        print(f"  评测 {case['id']}: {case['description'][:60]}...")
        result = await run_a2a_case(case, conn)
        results.append(result)
        status = "✅" if result["passed"] else "❌"
        print(f"    {status} agents={result['actual_agents']} depth={result['actual_depth']} "
              f"challenge={result['challenge_found']} chain={result['chain_completed']}")

    # ── 汇总 ──
    print("\n" + "=" * 70)
    print(f"{'ID':<12} {'通过':<6} {'Agents':<8} {'Depth':<8} {'Challenge':<12} {'Chain':<8} 备注")
    print("-" * 70)
    for r in results:
        icon = "✅" if r["passed"] else "❌"
        notes = ""
        if r["verdict_reasons"]:
            notes = ", ".join(r["verdict_reasons"])
        if r["error"]:
            notes = f"ERROR: {r['error'][:40]}"
        print(f"{r['id']:<12} {icon}     "
              f"{'OK' if r['agents_correct'] else 'FAIL':<8} "
              f"{'OK' if r['depth_ok'] else 'FAIL':<8} "
              f"{'OK' if r['challenge_found'] else 'FAIL':<12} "
              f"{'OK' if r['chain_completed'] else 'FAIL':<8} "
              f"{notes}")

    print("-" * 70)

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    agents_ok = sum(1 for r in results if r["agents_correct"])
    challenge_ok = sum(1 for r in results if r["challenge_found"])
    chain_ok = sum(1 for r in results if r["chain_completed"])
    loop_free = sum(1 for r in results if r["no_loop"])

    print(f"\nA2A 链路评测汇总：")
    print(f"  总体通过：{passed}/{total}  (验收线 ≥ 80%)")
    print(f"  Agent 路由正确：{agents_ok}/{total}")
    print(f"  挑战内容产出：{challenge_ok}/{total}")
    print(f"  链路正常终止：{chain_ok}/{total}")
    print(f"  无异常循环：{loop_free}/{total}")

    pass_rate = passed / total * 100
    challenge_rate = challenge_ok / total * 100

    if pass_rate >= 80 and challenge_rate >= 80:
        print("\n✅ PASS — A2A 链路黄金集验收通过")
        sys.exit(0)
    else:
        print("\n❌ FAIL — 未达验收标准")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
