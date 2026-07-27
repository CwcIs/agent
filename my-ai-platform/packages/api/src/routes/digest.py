"""Digest routes."""

import json
import sqlite3
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.routes.dependencies import get_conn

router = APIRouter()

async def _build_digest(conn: sqlite3.Connection, days: int, label: str) -> dict:
    """通用 digest 构建器：daily(7天) / weekly(30天) / monthly(90天)。"""
    since = (date.today() - timedelta(days=days)).isoformat()
    limit = 50 if days >= 30 else 30
    rows = conn.execute(
        "SELECT id, title, content, tags_json, created_at FROM notes "
        "WHERE status='live' AND knowledge_status='canonical' "
        "AND deleted_at IS NULL AND date(created_at) >= ? "
        "ORDER BY created_at DESC LIMIT ?",
        (since, limit),
    ).fetchall()

    note_count = len(rows)

    if note_count == 0:
        return {
            "label": label,
            "noteCount": 0,
            "narrative": "这个时间段还没有笔记，去 Chat 里写一条吧。",
            "followUps": ["我想开始记录想法", "帮我新建一条笔记", "笔记库能存什么内容？"],
            "citedNotes": [],
            "trends": [],
            "anomalies": [],
            "collisions": [],
        }

    notes_text = "\n\n".join(
        f"[{i+1}] id={dict(r)['id']}\n标题：{dict(r)['title']}\n内容：{dict(r)['content'][:300]}"
        for i, r in enumerate(rows)
    )

    prompt = f"""以下是用户最近 {days} 天的 {note_count} 条笔记：

{notes_text}

请生成：
1. 一段中文综述（自然段落，150字以内），指出知识演进或话题迁移
2. 恰好3条值得追问的问题
3. 1-2个趋势发现（如"话题X反复出现"、"从A→B→C的知识演进"）
4. 1-2个值得探索的方向

以 JSON 格式返回：
{{
  "narrative": "综述文字",
  "followUps": ["追问1", "追问2", "追问3"],
  "citedNotes": [{{"noteId": "id", "title": "标题"}}],
  "trends": ["趋势发现1", "趋势发现2"],
  "explore": ["值得探索的方向1"]
}}

只返回 JSON。"""

    from src.agent.providers.deepseek import make_deepseek
    llm = make_deepseek()
    try:
        response = await llm.ainvoke([SystemMessage(content="你是用户的个人知识助手，用中文回答。"), HumanMessage(content=prompt)])
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        parsed = json.loads(text)
    except Exception:
        parsed = {
            "narrative": response.content[:200] if 'response' in dir() else "分析生成失败",
            "followUps": [],
            "citedNotes": [],
            "trends": [],
            "explore": [],
        }

    # 待复习笔记
    due_reviews = conn.execute(
        """SELECT id, title, review_count, review_interval FROM notes
           WHERE status='live' AND knowledge_status='canonical'
             AND deleted_at IS NULL
             AND last_reviewed_at IS NOT NULL
             AND julianday('now') - julianday(last_reviewed_at) > review_interval
           LIMIT 5"""
    ).fetchall()

    # 写作建议
    tag_clusters: dict[str, list[str]] = {}
    for r in rows:
        for tag in json.loads(r["tags_json"] or "[]"):
            tag_clusters.setdefault(tag, []).append(r["id"])
    writing_suggestions = []
    for tag, nids in sorted(tag_clusters.items(), key=lambda x: -len(x[1])):
        if len(nids) >= 5:
            writing_suggestions.append({"topic": tag, "note_count": len(nids)})

    # 获取碰撞发现
    collision_rows = conn.execute(
        "SELECT id, note_a_id, note_b_id, score, connection, angle FROM idea_collisions "
        "WHERE created_at >= ? ORDER BY score DESC LIMIT 5",
        (since,),
    ).fetchall()

    # 异常检测（纯数据，不调 LLM）
    anomalies = _detect_anomalies_basic(conn, rows)

    return {
        "label": label,
        "noteCount": note_count,
        "narrative": parsed.get("narrative", ""),
        "followUps": parsed.get("followUps", []),
        "citedNotes": parsed.get("citedNotes", []),
        "trends": parsed.get("trends", []) + parsed.get("explore", []),
        "anomalies": anomalies,
        "dueReviews": [{"id": r["id"], "title": r["title"],
                         "review_count": r["review_count"] or 0,
                         "interval_days": r["review_interval"] or 1} for r in due_reviews],
        "writingSuggestions": writing_suggestions[:3],
        "collisions": [
            {
                "id": r["id"],
                "note_a_id": r["note_a_id"],
                "note_b_id": r["note_b_id"],
                "score": r["score"],
                "connection": r["connection"],
                "angle": r["angle"],
            }
            for r in collision_rows
        ],
    }


def _detect_anomalies_basic(conn: sqlite3.Connection, note_rows: list) -> list[str]:
    """简单异常检测：空白日 + 笔记爆发。纯数据计算。"""
    if len(note_rows) < 2:
        return []
    from collections import defaultdict
    by_day: dict[str, int] = defaultdict(int)
    for r in note_rows:
        day = dict(r)["created_at"][:10]
        by_day[day] += 1
    sorted_days = sorted(by_day.keys())
    anomalies: list[str] = []
    # 空白日
    if len(sorted_days) >= 3:
        start = date.fromisoformat(sorted_days[0])
        end = date.fromisoformat(sorted_days[-1])
        d = start
        while d <= end:
            if d.isoformat() not in by_day and d != date.today():
                anomalies.append(f"{d.isoformat()} 无新笔记")
                if len(anomalies) >= 2:
                    break
            d += timedelta(days=1)
    return anomalies[:3]


# ── GET /digest (daily) ───────────────────────────────────
@router.get("/digest")
async def get_digest(conn: sqlite3.Connection = Depends(get_conn)):
    today = date.today().isoformat()

    # 命中缓存直接返回
    cached = conn.execute(
        "SELECT note_count, narrative, follow_ups, cited_notes, trends, anomalies FROM daily_digests WHERE date = ?", (today,)
    ).fetchone()
    if cached:
        return {
            "label": "daily",
            "date": today,
            "noteCount": cached["note_count"],
            "narrative": cached["narrative"],
            "followUps": json.loads(cached["follow_ups"]),
            "citedNotes": json.loads(cached["cited_notes"]),
            "trends": json.loads(cached["trends"] if cached["trends"] else "[]"),
            "anomalies": json.loads(cached["anomalies"] if cached["anomalies"] else "[]"),
            "collisions": [],
        }

    result = await _build_digest(conn, 7, "daily")
    result["date"] = today
    _cache_digest(conn, today, result)
    return result


# ── GET /digest/weekly ────────────────────────────────────
@router.get("/digest/weekly")
async def get_weekly_digest(conn: sqlite3.Connection = Depends(get_conn)):
    """周回顾：最近 30 天笔记的 LLM 分析。"""
    return await _build_digest(conn, 30, "weekly")


# ── POST /digest/daily/generate ──────────────────────────
@router.post("/digest/daily/generate", status_code=201)
async def generate_digest(conn: sqlite3.Connection = Depends(get_conn)):
    """手动触发每日回顾生成（供外部 cron / Task Scheduler 调用）。
    返回生成的 digest 内容，前端可据此推送浏览器通知。"""
    today = date.today().isoformat()
    result = await _build_digest(conn, 7, "daily")
    result["date"] = today
    _cache_digest(conn, today, result)
    return {"status": "generated", "digest": result}


# ── GET /digest/monthly ───────────────────────────────────
@router.get("/digest/monthly")
async def get_monthly_digest(conn: sqlite3.Connection = Depends(get_conn)):
    """月回顾：最近 90 天笔记的 LLM 分析。"""
    return await _build_digest(conn, 90, "monthly")

def _cache_digest(conn: sqlite3.Connection, today: str, payload: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO daily_digests "
        "(id, date, note_count, narrative, follow_ups, cited_notes, trends, anomalies) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            today,
            payload.get("noteCount", 0),
            payload.get("narrative", ""),
            json.dumps(payload.get("followUps", []), ensure_ascii=False),
            json.dumps(payload.get("citedNotes", []), ensure_ascii=False),
            json.dumps(payload.get("trends", []), ensure_ascii=False),
            json.dumps(payload.get("anomalies", []), ensure_ascii=False),
        ),
    )
    conn.commit()
