# ============================================================
# user_profile.py — 用户画像聚合模块（Phase 6.5）
#
# 画像维度：
#   1. 兴趣分布 — 从 tags + 向量聚类提取 top 5-8 话题
#   2. 活跃时段 — 分析用户最活跃的时间
#   3. 思考风格 — 笔记偏"分析/批判"还是"发散/联想"
#   4. 知识盲区 — 用户可能回避或未涉及的话题
#   5. 常用 Agent — 哪些 Agent 被调用最频繁
#
# 使用：gather(conn) → dict
# 数据来源：notes / messages / llm_calls 表
# ============================================================

import json
import sqlite3
from collections import defaultdict
from datetime import date


def gather(conn: sqlite3.Connection) -> dict:
    """聚合现有数据，生成用户知识画像。"""

    # ── 1. 兴趣分布 ──
    tag_rows = conn.execute(
        "SELECT tags_json FROM notes WHERE status='live' AND deleted_at IS NULL"
    ).fetchall()
    tag_counts: dict[str, int] = defaultdict(int)
    for r in tag_rows:
        for tag in json.loads(r[0] or "[]"):
            tag_counts[tag] += 1
    top_interests = sorted(tag_counts.items(), key=lambda x: -x[1])[:8]

    # ── 2. 活跃时段 ──
    time_rows = conn.execute(
        "SELECT created_at FROM messages WHERE role='user' ORDER BY created_at DESC LIMIT 500"
    ).fetchall()
    hour_counts: dict[int, int] = defaultdict(int)
    dow_counts: dict[int, int] = defaultdict(int)  # day of week
    for r in time_rows:
        try:
            hour = int(r["created_at"][11:13])
            hour_counts[hour] += 1
            # 从 datetime 字符串提取星期
            from datetime import datetime
            dt = datetime.fromisoformat(r["created_at"])
            dow_counts[dt.weekday()] += 1
        except Exception:
            pass
    peak_hours = sorted(hour_counts.items(), key=lambda x: -x[1])[:3]
    active_days = sorted(dow_counts.items(), key=lambda x: -x[1])[:3]

    # ── 3. 思考风格 ──
    # 基于笔记内容的简单启发式分析
    style_scores = _analyze_thinking_style(conn)

    # ── 4. 知识覆盖维度 ──
    coverage = _analyze_coverage(conn, tag_counts)

    # ── 5. Agent 使用统计 ──
    agent_rows = conn.execute(
        "SELECT agent_id, COUNT(*) as cnt, SUM(cost_usd) as cost "
        "FROM llm_calls WHERE agent_id != '' "
        "GROUP BY agent_id ORDER BY cnt DESC"
    ).fetchall()
    agent_usage = [
        {"agent": r["agent_id"], "calls": r["cnt"], "cost_usd": round(r["cost"] or 0, 4)}
        for r in agent_rows
    ]

    # ── 6. 笔记总量统计 ──
    total_live = conn.execute(
        "SELECT COUNT(*) FROM notes WHERE status='live' AND deleted_at IS NULL"
    ).fetchone()[0]
    total_archived = conn.execute(
        "SELECT COUNT(*) FROM notes WHERE status='archived' AND deleted_at IS NULL"
    ).fetchone()[0]
    total_superseded = conn.execute(
        "SELECT COUNT(*) FROM notes WHERE status='superseded' AND deleted_at IS NULL"
    ).fetchone()[0]
    total_edges = conn.execute(
        "SELECT COUNT(*) FROM edges WHERE status='confirmed'"
    ).fetchone()[0]
    total_collisions = conn.execute(
        "SELECT COUNT(*) FROM idea_collisions"
    ).fetchone()[0]

    # ── 7. 笔记时间分布 ──
    monthly_rows = conn.execute(
        """SELECT substr(created_at, 1, 7) as month, COUNT(*) as cnt
           FROM notes WHERE deleted_at IS NULL
           GROUP BY month ORDER BY month DESC LIMIT 12"""
    ).fetchall()
    monthly_counts = [{"month": r["month"], "count": r["cnt"]} for r in monthly_rows]

    # ── 8. LLM 总成本 ──
    cost_row = conn.execute(
        "SELECT SUM(cost_usd) as total, COUNT(*) as total_calls FROM llm_calls"
    ).fetchone()
    total_cost = round(cost_row["total"] or 0, 4)
    total_calls = cost_row["total_calls"] or 0

    return {
        "interests": [{"tag": t, "count": c} for t, c in top_interests],
        "peak_hours": [{"hour": h, "count": c} for h, c in peak_hours],
        "active_days": [
            {"day": ["周一","周二","周三","周四","周五","周六","周日"][d], "count": c}
            for d, c in active_days
        ],
        "thinking_style": style_scores,
        "knowledge_coverage": coverage,
        "agent_usage": agent_usage,
        "notes": {
            "live": total_live,
            "archived": total_archived,
            "superseded": total_superseded,
            "edges": total_edges,
            "collisions": total_collisions,
        },
        "note_timeline": monthly_counts,
        "cost": {
            "total_usd": total_cost,
            "total_calls": total_calls,
        },
    }


def _analyze_thinking_style(conn: sqlite3.Connection) -> dict:
    """启发式分析思考风格：基于内容关键词统计。"""
    rows = conn.execute(
        "SELECT content FROM notes WHERE status='live' AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 100"
    ).fetchall()

    if not rows:
        return {"analytical": 0.5, "divergent": 0.5, "practical": 0.5, "label": "数据不足"}

    all_text = " ".join(dict(r)["content"][:500] for r in rows).lower()

    analytical_keywords = ["分析", "原因", "逻辑", "证据", "数据", "结构", "框架", "定义", "根本", "前提"]
    divergent_keywords = ["联想", "可能", "如果", "探索", "创意", "类比", "想象", "发散", "换个角度", "有趣"]
    practical_keywords = ["行动", "步骤", "方案", "实践", "操作", "工具", "todo", "计划", "目标", "结果"]

    def score(kws: list[str]) -> float:
        hits = sum(1 for kw in kws if kw in all_text)
        return round(0.3 + min(hits / max(len(kws), 1) * 0.7, 0.7), 2)

    analytical = score(analytical_keywords)
    divergent = score(divergent_keywords)
    practical = score(practical_keywords)

    # 决定标签
    scores = {"analytical": analytical, "divergent": divergent, "practical": practical}
    label_map = {"analytical": "分析型", "divergent": "发散型", "practical": "实践型"}
    primary = max(scores, key=scores.get)

    return {**scores, "label": label_map[primary]}


def _analyze_coverage(conn: sqlite3.Connection, tag_counts: dict[str, int]) -> dict:
    """分析知识覆盖维度。"""
    dimensions = {
        "技术": ["技术", "代码", "编程", "AI", "系统", "架构"],
        "商业": ["商业", "市场", "增长", "产品", "定价", "盈利"],
        "人文": ["哲学", "心理学", "历史", "文化", "艺术", "伦理"],
        "个人成长": ["学习", "效率", "习惯", "反思", "目标"],
        "创作输出": ["写作", "设计", "创作", "笔记", "表达"],
    }

    coverage = {}
    for dim, kws in dimensions.items():
        count = sum(tag_counts.get(kw, 0) for kw in kws)
        coverage[dim] = {"note_count": count, "level": "丰富" if count >= 5 else ("有涉猎" if count >= 2 else "空白")}

    return {"dimensions": coverage, "total_dimensions_with_content": sum(1 for v in coverage.values() if v["note_count"] >= 2)}
