"""User profile routes."""

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

@router.get("/user/profile")
def get_user_profile(conn: sqlite3.Connection = Depends(get_conn)):
    """返回用户知识画像：兴趣分布、活跃时段、思考风格、常用 Agent。"""
    from src.agent.user_profile import gather
    return gather(conn)


# ── GET /user/smart-badges ──────────────────────────────
@router.get("/user/smart-badges")
def get_smart_badges(conn: sqlite3.Connection = Depends(get_conn)):
    """返回智能提醒：待复习、碰撞发现、知识缺口、写作建议。适合前端轮询。"""
    badges: list[dict] = []

    # 待复习
    due = conn.execute(
        """SELECT COUNT(*) as cnt FROM notes
           WHERE status='live' AND deleted_at IS NULL
             AND last_reviewed_at IS NOT NULL
             AND julianday('now') - julianday(last_reviewed_at) > review_interval"""
    ).fetchone()
    if due and due["cnt"] > 0:
        badges.append({"type": "review", "label": f"{due['cnt']} 条笔记待复习", "priority": "high"})

    # 未读碰撞
    collisions = conn.execute(
        "SELECT COUNT(*) as cnt FROM idea_collisions WHERE is_read = 0"
    ).fetchone()
    if collisions and collisions["cnt"] > 0:
        badges.append({"type": "collision", "label": f"{collisions['cnt']} 个意外关联未读", "priority": "medium"})

    # 冷门话题（7 天未更新）
    stale = conn.execute(
        """SELECT COUNT(*) as cnt FROM notes
           WHERE status='live' AND deleted_at IS NULL
             AND julianday('now') - julianday(created_at) BETWEEN 7 AND 30
             AND id NOT IN (
               SELECT note_a_id FROM idea_collisions
               UNION SELECT note_b_id FROM idea_collisions
             )"""
    ).fetchone()
    if stale and stale["cnt"] > 5:
        badges.append({"type": "explore", "label": f"{stale['cnt']} 条笔记超过 7 天未被关联", "priority": "low"})

    # pending suggestions
    pending = conn.execute(
        "SELECT COUNT(*) as cnt FROM pending_suggestions WHERE status='pending'"
    ).fetchone()
    if pending and pending["cnt"] > 0:
        badges.append({"type": "suggestion", "label": f"{pending['cnt']} 条建议等待确认", "priority": "medium"})

    return {"badges": badges}

