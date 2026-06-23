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

import asyncio
import json
import sqlite3
import uuid
from typing import Optional

from langchain_core.tools import tool
from src.lib.embeddings import upsert_embedding, search_similar


async def _background_embed(conn: sqlite3.Connection, note_id: str, title: str, content: str) -> None:
    """后台异步写入向量 embedding，失败静默忽略。"""
    try:
        await upsert_embedding(conn, note_id, f"{title}\n{content}")
    except Exception:
        pass


def make_tools(conn: sqlite3.Connection) -> list:
    """
    工厂函数：传入 db 连接，返回绑定了连接的工具列表。
    这样 react_tool_loop.py 只需要调 make_tools(conn) 就拿到两个工具。
    """

    @tool
    async def search_notes(query: str, k: int = 5) -> str:
        """
        搜索笔记库，返回最多 k 条相关笔记（JSON 字符串）。
        优先使用语义向量搜索；若向量表为空则 fallback 到关键词检索。
        只返回 status='live' 的笔记。
        """
        results = []

        # 尝试向量搜索
        try:
            hits = await search_similar(conn, query, k)
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
    async def save_note(title: str, content: str, tags: Optional[str] = "") -> str:
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
        # 后台异步写入 embedding，不阻塞 save_note 返回
        asyncio.create_task(_background_embed(conn, note_id, title, content))
        return json.dumps({"status": "ok", "id": note_id, "title": title}, ensure_ascii=False)

    @tool
    def get_note(note_id: str) -> str:
        """
        按 ID 读取一条笔记的完整内容（title + content + tags + 时间）。
        note_id 可以是完整 UUID 或前 8 位前缀。
        用户说"看一下那条笔记"、"展开笔记 xxx"、"读一下 xxx"时优先调用。
        返回 JSON：{id, title, content, tags, status, created_at, updated_at}
        """
        # 支持前缀匹配
        if len(note_id) >= 8:
            rows = conn.execute(
                "SELECT id, title, content, tags_json, status, created_at, updated_at "
                "FROM notes WHERE id LIKE ? AND deleted_at IS NULL LIMIT 2",
                (note_id + "%",),
            ).fetchall()
            if len(rows) == 1:
                r = rows[0]
            elif len(rows) > 1:
                # 多个匹配，要求更精确的 ID
                row = conn.execute(
                    "SELECT id, title, content, tags_json, status, created_at, updated_at "
                    "FROM notes WHERE id = ? AND deleted_at IS NULL",
                    (note_id,),
                ).fetchone()
                r = row
            else:
                r = None
        else:
            r = conn.execute(
                "SELECT id, title, content, tags_json, status, created_at, updated_at "
                "FROM notes WHERE id = ? AND deleted_at IS NULL",
                (note_id,),
            ).fetchone()

        if not r:
            return json.dumps({"error": f"笔记 {note_id} 不存在或已删除"}, ensure_ascii=False)

        d = dict(r)
        d["tags"] = json.loads(d.pop("tags_json", "[]"))
        return json.dumps(d, ensure_ascii=False)

    @tool
    def archive_note(note_id: str) -> str:
        """
        归档一条笔记（标记为 archived，不再参与搜索和合成）。
        用户说"归档这条"、"这条笔记过时了"时调用。
        返回 JSON：{status: "archived", id: note_id}
        """
        row = conn.execute(
            "SELECT id FROM notes WHERE id = ? AND deleted_at IS NULL AND status != 'archived'",
            (note_id,),
        ).fetchone()
        if not row:
            return json.dumps({"error": f"笔记 {note_id} 不存在、已删除或已归档"}, ensure_ascii=False)

        conn.execute(
            "UPDATE notes SET status='archived', updated_at=datetime('now','localtime') WHERE id=?",
            (note_id,),
        )
        conn.commit()
        return json.dumps({"status": "archived", "id": note_id}, ensure_ascii=False)

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

    @tool
    async def synthesize_notes(topic: str, k: int = 6) -> str:
        """
        跨笔记综合：找到与 topic 最相关的笔记，生成一段综合洞察。
        适合用户问"我对 X 有哪些理解"、"总结一下我关于 X 的想法"、"X 方面我记了什么"。
        返回 JSON：{ narrative, cited_notes, gaps }
        - narrative: 综合分析段落
        - cited_notes: 引用的笔记列表 [{id, title}]
        - gaps: AI 发现的空白或矛盾点（1-2 条）
        """
        from src.lib.embeddings import search_similar
        from src.agent.providers.deepseek import make_deepseek

        # 向量搜索相关笔记
        try:
            hits = await search_similar(conn, topic, k)
            ids = [h["note_id"] for h in hits]
        except Exception:
            ids = []

        # fallback FTS5
        if not ids:
            rows = conn.execute(
                "SELECT n.id FROM notes_fts f JOIN notes n ON n.rowid = f.rowid "
                "WHERE notes_fts MATCH ? AND n.status='live' AND n.deleted_at IS NULL LIMIT ?",
                (topic, k),
            ).fetchall()
            ids = [r[0] for r in rows]

        if not ids:
            return json.dumps({
                "narrative": f"笔记库里还没有关于「{topic}」的内容。",
                "cited_notes": [],
                "gaps": [f"可以开始记录关于「{topic}」的想法"],
            }, ensure_ascii=False)

        placeholders = ",".join("?" * len(ids))
        notes = conn.execute(
            f"SELECT id, title, content FROM notes WHERE id IN ({placeholders}) "
            f"AND status='live' AND deleted_at IS NULL",
            ids,
        ).fetchall()

        notes_text = "\n\n".join(
            f"[{i+1}] 标题：{dict(n)['title']}\n内容：{dict(n)['content'][:400]}"
            for i, n in enumerate(notes)
        )

        prompt = f"""用户想了解自己关于「{topic}」的思考。以下是相关笔记：

{notes_text}

请生成：
1. 一段综合分析（自然段落，150字以内，指出共同主题、有趣联系）
2. 1-2 个空白或矛盾点（用户可能没想清楚的地方）

以 JSON 返回：
{{"narrative": "综合分析", "gaps": ["空白点1", "空白点2"]}}

只返回 JSON。"""

        llm = make_deepseek()

        async def _call():
            from langchain_core.messages import HumanMessage
            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            return resp.content

        try:
            text = await _call()

            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            parsed = json.loads(text)
        except Exception as e:
            parsed = {"narrative": f"综合分析生成失败：{e}", "gaps": []}

        return json.dumps({
            "narrative": parsed.get("narrative", ""),
            "cited_notes": [{"id": dict(n)["id"], "title": dict(n)["title"]} for n in notes],
            "gaps": parsed.get("gaps", []),
        }, ensure_ascii=False)

    return [search_notes, save_note, get_note, archive_note, get_notes_summary, synthesize_notes]
