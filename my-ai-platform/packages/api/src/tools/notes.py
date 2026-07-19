"""Core note Agent tools."""

import asyncio
import json
import re
import sqlite3
import uuid
from typing import Optional

from langchain_core.tools import tool

from src.lib.embeddings import search_similar, upsert_embedding
from src.tools._shared import (
    TOOL_TIMEOUT,
    _background_embed,
    _create_wikilink_edges,
    _parse_wikilinks,
    _resolve_title_to_id,
    _task_done_callback,
)

def build_note_tools(conn: sqlite3.Connection) -> list:
    @tool
    async def search_notes(query: str, k: int = 5) -> str:
        """
        搜索笔记库，返回最多 k 条相关笔记（JSON 字符串）。
        使用语义搜索 + 关键词检索 → 统一多因子排序（Bayesian + Decay + Graph）。
        只返回 status='live' 的笔记。
        """
        from src.lib.ranker import rank_candidates, record_event

        k = min(k, 10)
        candidates: list[dict] = []
        semantic_scores: dict[str, float] = {}
        keyword_scores: dict[str, float] = {}

        # 向量搜索（审计 R1：asyncio.wait_for 超时 10s）
        try:
            hits = await asyncio.wait_for(search_similar(conn, query, k * 2), timeout=TOOL_TIMEOUT)
            if hits:
                ids = [h["note_id"] for h in hits]
                # distance → similarity mapping for normalized L2
                for h in hits:
                    sim = max(0.0, 1.0 - (h["distance"] * h["distance"]) / 2.0)
                    semantic_scores[h["note_id"]] = round(sim, 3)

                placeholders = ",".join("?" * len(ids))
                rows = conn.execute(
                    f"SELECT id, title, content, tags_json, created_at FROM notes "
                    f"WHERE id IN ({placeholders}) AND status='live' AND deleted_at IS NULL",
                    ids,
                ).fetchall()
                for r in rows:
                    d = dict(r)
                    candidates.append(d)
        except asyncio.TimeoutError:
            return json.dumps({"status": "error", "message": f"向量搜索超时（>{TOOL_TIMEOUT}s）"}, ensure_ascii=False)
        except Exception:
            pass

        # FTS5 关键词检索作为补充
        escaped = '"' + query.replace('"', '""') + '"'
        try:
            fts_rows = conn.execute(
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
                (escaped, k * 2),
            ).fetchall()
            for idx, r in enumerate(fts_rows):
                d = dict(r)
                nid = d["id"]
                if nid not in {c["id"] for c in candidates}:
                    candidates.append(d)
                # 排名越前关键词分越高
                rank_norm = max(0.0, 1.0 - idx / max(len(fts_rows), 1))
                keyword_scores[nid] = round(rank_norm, 3)
        except Exception:
            pass

        if not candidates:
            return json.dumps([], ensure_ascii=False)

        # 统一排序
        ranked = rank_candidates(conn, candidates, semantic_scores, keyword_scores)
        top = ranked[:k]

        # 记录 shown 事件
        for c in top:
            try:
                record_event(conn, c["id"], "shown", source="search")
            except Exception:
                pass

        # 格式化输出
        results = []
        for c in top:
            raw = c.get("content", "")
            c["content"] = raw[:300] + ("..." if len(raw) > 300 else "")
            c["tags"] = json.loads(c.pop("tags_json", "[]"))
            c["_ranker"] = c.get("_ranker", {})
            results.append(c)

        return json.dumps(results, ensure_ascii=False)

    @tool
    async def save_note(title: str, content: str, tags: Optional[str] = "", supersedes_id: Optional[str] = "") -> str:
        """
        把一条新笔记保存到笔记库。
        tags 用逗号分隔，例如 '产品,增长'。
        内容中的 [[笔记标题]] 语法会自动创建双链关系。
        supersedes_id 可选：传入旧笔记 ID 表示本笔记替代/升级了旧笔记，会自动创建 evolved_from 关系并将旧笔记标记为 superseded。
        返回新笔记的 id 和创建的双链边。
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

        # ── [[wikilink]] 自动解析 → 写入 edges ──
        wikilink_titles = _parse_wikilinks(content)
        edges_created = _create_wikilink_edges(conn, note_id, wikilink_titles)

        # ── Phase 4A-1：supersedes_id → evolved_from edge + 标记旧笔记 ──
        superseded_title = ""
        if supersedes_id and supersedes_id.strip():
            old_row = conn.execute(
                "SELECT id, title FROM notes WHERE id = ? AND deleted_at IS NULL",
                (supersedes_id.strip(),),
            ).fetchone()
            if old_row:
                superseded_title = old_row["title"]
                # 标记旧笔记为 superseded
                conn.execute(
                    "UPDATE notes SET status='superseded', superseded_by=?, updated_at=datetime('now','localtime') WHERE id=?",
                    (note_id, old_row["id"]),
                )
                # 创建 evolved_from edge
                edge_id = str(uuid.uuid4())
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO edges
                           (id, from_id, to_id, relation, confidence, source, evidence, status)
                           VALUES (?, ?, ?, 'evolved_from', 1.0, 'manual', ?, 'confirmed')""",
                        (edge_id, old_row["id"], note_id, f"superseded by note {note_id}"),
                    )
                    conn.commit()
                    edges_created.append({"id": edge_id, "from_id": old_row["id"], "to_id": note_id, "relation": "evolved_from", "to_title": title})
                except Exception:
                    pass
            conn.commit()

        # 后台异步写入 embedding + 相似度检测，不阻塞 save_note 返回
        task = asyncio.create_task(_background_embed(conn, note_id, title, content))
        _background_tasks.add(task)
        task.add_done_callback(_task_done_callback)
        return json.dumps({
            "status": "ok", "id": note_id, "title": title,
            "edges_created": len(edges_created),
            "superseded_title": superseded_title,
        }, ensure_ascii=False)

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
            return json.dumps({"status": "error", "message": f"笔记 {note_id} 不存在或已删除"}, ensure_ascii=False)

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
            return json.dumps({"status": "error", "message": f"笔记 {note_id} 不存在、已删除或已归档"}, ensure_ascii=False)

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

        # 向量搜索相关笔记（审计 R1：asyncio.wait_for 超时）
        try:
            hits = await asyncio.wait_for(search_similar(conn, topic, k), timeout=TOOL_TIMEOUT)
            ids = [h["note_id"] for h in hits]
        except asyncio.TimeoutError:
            return json.dumps({"status": "error", "message": f"向量搜索超时（>{TOOL_TIMEOUT}s），请缩小话题范围重试"}, ensure_ascii=False)
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
            # 审计 R1：LLM 调用加超时
            text = await asyncio.wait_for(_call(), timeout=TOOL_TIMEOUT)

            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            parsed = json.loads(text)
        except asyncio.TimeoutError:
            parsed = {"narrative": f"综合分析 LLM 调用超时（>{TOOL_TIMEOUT}s），请稍后重试", "gaps": []}
        except Exception as e:
            parsed = {"narrative": f"综合分析生成失败：{e}", "gaps": []}

        return json.dumps({
            "narrative": parsed.get("narrative", ""),
            "cited_notes": [{"id": dict(n)["id"], "title": dict(n)["title"]} for n in notes],
            "gaps": parsed.get("gaps", []),
        }, ensure_ascii=False)

    return [search_notes, save_note, get_note, archive_note, get_notes_summary, synthesize_notes]

