# ============================================================
# ToolRegistry — LangChain Tool 定义
# 对应 MD §3.3.1 ToolDef 接口 + §8.3 Agent 原理验收
#
# Phase 1 工具（两个）：
#   search_notes(query, k=5)   — FTS5 关键字检索，Phase 2 升级为向量
#   save_note({title, content, tags}) — 写入 SQLite notes 表
#
# 每个 tool 用 langchain_core.tools.tool 装饰器定义，
# 底层是 zod/pydantic schema + async 函数。
#
# LangChain Tool 形态（MD §5.2 取舍说明）：
#   - 只借用 Schema 形态（pydantic → JSON Schema 给模型）
#   - 不用 AgentExecutor / Chain（会把 tool loop 黑盒化，
#     导致"用了 Agent 但没看见 Agent"）
#   - Tool Loop 自己手写在 react_tool_loop.py
# ============================================================

import json
import sqlite3
import uuid
from typing import Optional

from langchain_core.tools import tool
from src.lib.embeddings import upsert_embedding, search_similar


def make_tools(conn: sqlite3.Connection) -> list:
    """
    工厂函数：传入 db 连接，返回绑定了连接的工具列表。
    这样 react_tool_loop.py 只需要调 make_tools(conn) 就拿到两个工具。
    """

    @tool
    def search_notes(query: str, k: int = 5) -> str:
        """
        搜索笔记库，返回最多 k 条相关笔记（JSON 字符串）。
        优先使用语义向量搜索；若向量表为空则 fallback 到关键词检索。
        只返回 status='live' 的笔记。
        """
        results = []

        # 尝试向量搜索
        try:
            hits = search_similar(conn, query, k)
            if hits:
                ids = [h["note_id"] for h in hits]
                placeholders = ",".join("?" * len(ids))
                rows = conn.execute(
                    f"SELECT id, title, content, tags_json, created_at FROM notes "
                    f"WHERE id IN ({placeholders}) AND status='live' AND deleted_at IS NULL",
                    ids,
                ).fetchall()
                id_order = {nid: i for i, nid in enumerate(ids)}
                rows_sorted = sorted(rows, key=lambda r: id_order.get(dict(r)["id"], 999))
                for r in rows_sorted:
                    d = dict(r)
                    d["tags"] = json.loads(d.pop("tags_json", "[]"))
                    results.append(d)
        except Exception:
            pass

        # fallback：FTS5 关键词检索
        if not results:
            rows = conn.execute(
                """
                SELECT n.id, n.title, n.content, n.tags_json, n.created_at
                FROM notes_fts f
                JOIN notes n ON n.rowid = f.rowid
                WHERE notes_fts MATCH ?
                  AND n.status = 'live'
                  AND n.deleted_at IS NULL
                ORDER BY rank
                LIMIT ?
                """,
                (query, k),
            ).fetchall()
            for r in rows:
                d = dict(r)
                d["tags"] = json.loads(d.pop("tags_json", "[]"))
                results.append(d)

        return json.dumps(results, ensure_ascii=False)

    @tool
    def save_note(title: str, content: str, tags: Optional[str] = "") -> str:
        """
        把一条新笔记保存到笔记库。
        tags 用逗号分隔，例如 '产品,增长'。
        返回新笔记的 id。
        """
        note_id = str(uuid.uuid4())
        tags_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        conn.execute(
            """
            INSERT INTO notes (id, title, content, tags_json)
            VALUES (?, ?, ?, ?)
            """,
            (note_id, title, content, json.dumps(tags_list, ensure_ascii=False)),
        )
        conn.commit()
        try:
            upsert_embedding(conn, note_id, f"{title}\n{content}")
        except Exception:
            pass
        return json.dumps({"status": "ok", "id": note_id, "title": title}, ensure_ascii=False)

    @tool
    def get_notes_summary() -> str:
        """
        获取笔记库的聚合统计摘要：总数、最近7天新增、各标签分布。
        用户问"我有什么笔记"、"笔记概况"、"笔记库里有什么"时优先调用此工具。
        """
        total = conn.execute(
            "SELECT COUNT(*) FROM notes WHERE status='live' AND deleted_at IS NULL"
        ).fetchone()[0]

        recent = conn.execute(
            "SELECT COUNT(*) FROM notes WHERE status='live' AND deleted_at IS NULL "
            "AND created_at >= datetime('now', '-7 days')"
        ).fetchone()[0]

        tag_rows = conn.execute(
            "SELECT tags_json FROM notes WHERE status='live' AND deleted_at IS NULL"
        ).fetchall()
        tag_counts: dict[str, int] = {}
        for row in tag_rows:
            for tag in json.loads(row[0] or "[]"):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:8]
        tags_str = "、".join(f"{t}({n})" for t, n in top_tags) if top_tags else "暂无标签"

        return json.dumps({
            "total": total,
            "recent_7d": recent,
            "top_tags": tags_str,
        }, ensure_ascii=False)

    return [search_notes, save_note, get_notes_summary]
