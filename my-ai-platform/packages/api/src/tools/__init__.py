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


def make_tools(conn: sqlite3.Connection) -> list:
    """
    工厂函数：传入 db 连接，返回绑定了连接的工具列表。
    这样 react_tool_loop.py 只需要调 make_tools(conn) 就拿到两个工具。
    """

    @tool
    def search_notes(query: str, k: int = 5) -> str:
        """
        用关键词搜索笔记库，返回最多 k 条匹配笔记（JSON 字符串）。
        搜索范围：标题 + 正文全文检索（FTS5）。
        只返回 status='live' 的笔记。
        """
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
        results = [dict(r) for r in rows]
        # tags_json 是 JSON 字符串，解析成列表方便模型读
        for r in results:
            r["tags"] = json.loads(r.pop("tags_json", "[]"))
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
