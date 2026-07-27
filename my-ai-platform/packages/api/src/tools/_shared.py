"""Shared helpers for note-oriented Agent tools."""

import asyncio
import json
import re
import sqlite3
import uuid
from typing import Optional

from langchain_core.tools import tool
from src.lib.embeddings import upsert_embedding, search_similar


# ── 工具调用超时（审计 R1）──
# 每次异步工具调用配 asyncio.wait_for(timeout=10s)，
# 防止 search_notes / synthesize_notes 慢查询永久挂住。
TOOL_TIMEOUT = 10  # 秒

# 持有后台任务引用，防止被 GC 取消导致 embedding 静默丢失
_background_tasks: set[asyncio.Task] = set()

# ── [[wikilink]] 解析 ──
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _parse_wikilinks(content: str) -> list[str]:
    """从笔记内容中提取所有 [[双链]] 引用的标题，去重保持出现顺序。"""
    titles = _WIKILINK_RE.findall(content)
    seen: set[str] = set()
    unique: list[str] = []
    for t in titles:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def _resolve_title_to_id(conn: sqlite3.Connection, title: str) -> str | None:
    """按标题精确匹配查找笔记 ID。多条同名笔记时返回最近更新的。"""
    rows = conn.execute(
        "SELECT id FROM notes WHERE title = ? AND knowledge_status='canonical' "
        "AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT 1",
        (title,),
    ).fetchall()
    return rows[0][0] if rows else None


def _create_wikilink_edges(conn: sqlite3.Connection, from_id: str, titles: list[str]) -> list[dict]:
    """为 from_id 笔记创建指向 [[title]] 目标笔记的 wikilink edges。返回创建的 edge 列表。"""
    created: list[dict] = []
    for title in titles:
        to_id = _resolve_title_to_id(conn, title)
        if not to_id or to_id == from_id:
            continue  # 目标不存在或自引用，静默跳过
        edge_id = str(uuid.uuid4())
        try:
            conn.execute(
                "INSERT OR IGNORE INTO edges (id, from_id, to_id, relation) VALUES (?, ?, ?, 'wikilink')",
                (edge_id, from_id, to_id),
            )
            conn.commit()
            # 检查是否真的插入了（OR IGNORE 可能跳过重复）
            row = conn.execute("SELECT id FROM edges WHERE id = ?", (edge_id,)).fetchone()
            if row:
                created.append({"id": edge_id, "from_id": from_id, "to_id": to_id, "relation": "wikilink", "to_title": title})
        except Exception:
            pass  # edge 创建失败不阻塞笔记保存
    return created


def _task_done_callback(task: asyncio.Task) -> None:
    """任务完成后从集合中移除引用。"""
    _background_tasks.discard(task)


async def _background_embed(conn: sqlite3.Connection, note_id: str, title: str, content: str) -> None:
    """后台异步写入向量 embedding + 自动检测相似笔记，失败静默忽略。"""
    try:
        await upsert_embedding(conn, note_id, f"{title}\n{content}")

        # Phase 4A-1：查找与新笔记最相似的 top 5 已有笔记
        from src.lib.embeddings import search_similar
        hits = await search_similar(conn, f"{title}\n{content}", k=5)
        for h in hits:
            if h["note_id"] == note_id:
                continue  # 跳过自己（刚写入的向量）
            # normalized L2: distance 0=identical, 2=opposite
            # similarity ≈ 1 - distance²/2
            dist = h["distance"]
            sim = 1.0 - (dist * dist) / 2.0

            if sim > 0.82:
                # 高相似度：直接创建 suggested similar edge
                edge_id = str(uuid.uuid4())
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO edges
                           (id, from_id, to_id, relation, confidence, source, evidence, status)
                           VALUES (?, ?, ?, 'similar', ?, 'embedding', ?, 'suggested')""",
                        (edge_id, note_id, h["note_id"], round(sim, 3),
                         f"embedding similarity {sim:.3f} (distance={dist:.4f})"),
                    )
                    conn.commit()
                except Exception:
                    pass
            elif sim > 0.5:
                # 中等相似度：存入 pending_suggestions 等用户确认
                sid = str(uuid.uuid4())
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO pending_suggestions
                           (id, from_id, to_id, relation, confidence, evidence, suggestion_type)
                           VALUES (?, ?, ?, 'similar', ?, ?, 'relation')""",
                        (sid, note_id, h["note_id"], round(sim, 3),
                         f"embedding similarity {sim:.3f} (distance={dist:.4f})"),
                    )
                    conn.commit()
                except Exception:
                    pass
    except Exception:
        pass
