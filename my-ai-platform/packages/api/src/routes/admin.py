"""Administration routes."""

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

@router.get("/admin/stats")
def admin_stats(conn: sqlite3.Connection = Depends(get_conn)):
    """聚合统计数据：笔记数、成本、调用次数、错误率。"""
    total_notes = conn.execute("SELECT COUNT(*) FROM notes WHERE deleted_at IS NULL").fetchone()[0]
    live_notes = conn.execute("SELECT COUNT(*) FROM notes WHERE status='live' AND deleted_at IS NULL").fetchone()[0]
    total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    total_collisions = conn.execute("SELECT COUNT(*) FROM idea_collisions").fetchone()[0]

    today = date.today().isoformat()
    today_calls = conn.execute(
        "SELECT COUNT(*), SUM(cost_usd) FROM llm_calls WHERE date(created_at) = ?", (today,)
    ).fetchone()
    week_calls = conn.execute(
        "SELECT COUNT(*), SUM(cost_usd) FROM llm_calls WHERE date(created_at) >= ?",
        ((date.today() - timedelta(days=7)).isoformat(),),
    ).fetchone()

    model_stats = conn.execute(
        "SELECT model, COUNT(*) as cnt, SUM(cost_usd) as cost FROM llm_calls GROUP BY model ORDER BY cnt DESC"
    ).fetchall()

    agent_stats = conn.execute(
        "SELECT agent_id, COUNT(*) as cnt FROM llm_calls WHERE agent_id != '' GROUP BY agent_id ORDER BY cnt DESC"
    ).fetchall()

    error_count = conn.execute(
        "SELECT COUNT(*) FROM llm_errors WHERE date(created_at) = ?", (today,)
    ).fetchone()[0]

    # DB size
    import os as _os
    from pathlib import Path
    db_path = Path(__file__).parent.parent.parent / "data" / "app.db"
    db_size_mb = round(_os.path.getsize(str(db_path)) / (1024 * 1024), 2) if db_path.exists() else 0

    return {
        "notes": {"total": total_notes, "live": live_notes, "edges": total_edges, "collisions": total_collisions},
        "costs": {
            "today_calls": today_calls[0] or 0,
            "today_cost_usd": round(today_calls[1] or 0, 4),
            "week_calls": week_calls[0] or 0,
            "week_cost_usd": round(week_calls[1] or 0, 4),
        },
        "models": [{"model": r["model"], "calls": r["cnt"], "cost_usd": round(r["cost"] or 0, 4)} for r in model_stats],
        "agents": [{"agent": r["agent_id"], "calls": r["cnt"]} for r in agent_stats],
        "errors_today": error_count,
        "db_size_mb": db_size_mb,
    }


@router.get("/admin/errors")
def admin_errors(limit: int = 50, conn: sqlite3.Connection = Depends(get_conn)):
    """最近错误列表。"""
    rows = conn.execute(
        "SELECT e.id, e.error_type, e.error_msg, e.created_at, "
        "c.agent_id, c.model "
        "FROM llm_errors e "
        "LEFT JOIN llm_calls c ON c.id = e.llm_call_id "
        "ORDER BY e.created_at DESC LIMIT ?",
        (min(limit, 100),),
    ).fetchall()
    return {"errors": [dict(r) for r in rows]}


@router.get("/admin/health")
def admin_health(conn: sqlite3.Connection = Depends(get_conn)):
    """系统健康检查。"""
    import os as _os
    import sys as _sys

    # Check vector model
    try:
        from src.lib.embeddings import search_similar, ensure_vec_table
        ensure_vec_table(conn)
        coverage = conn.execute(
            "SELECT COUNT(DISTINCT ne.note_id) FROM note_embeddings ne"
        ).fetchone()[0]
        total_live = conn.execute(
            "SELECT COUNT(*) FROM notes WHERE status='live' AND deleted_at IS NULL"
        ).fetchone()[0]
        vec_status = "ok" if coverage > 0 else "no_embeddings"
        coverage_pct = round(coverage / max(total_live, 1) * 100, 1)
    except Exception as e:
        vec_status = f"error: {e}"
        coverage_pct = 0

    # Check LLM providers
    providers = {}
    for name, key_var in [("deepseek", "DEEPSEEK_API_KEY"), ("openai", "OPENAI_API_KEY"), ("gemini", "GOOGLE_API_KEY")]:
        providers[name] = "ok" if _os.environ.get(key_var) else "missing"

    return {
        "status": "ok",
        "vector_model": {"status": vec_status, "coverage_pct": coverage_pct},
        "providers": providers,
        "python_version": _sys.version.split()[0],
    }

