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
        "SELECT id FROM notes WHERE title = ? AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT 1",
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
        每篇笔记内容截断至 300 字，防止大笔记库撑爆上下文（审计 A1）。
        """
        k = min(k, 10)  # 上限 10 条，防止大结果集撑爆上下文
        results = []

        # 尝试向量搜索（审计 R1：asyncio.wait_for 超时 10s）
        try:
            hits = await asyncio.wait_for(search_similar(conn, query, k), timeout=TOOL_TIMEOUT)
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
                    raw = d.get("content", "")
                    d["content"] = raw[:300] + ("..." if len(raw) > 300 else "")
                    d["tags"] = json.loads(d.pop("tags_json", "[]"))
                    results.append(d)
        except asyncio.TimeoutError:
            return json.dumps({"status": "error", "message": f"向量搜索超时（>{TOOL_TIMEOUT}s），请缩小查询范围重试"}, ensure_ascii=False)
        except Exception:
            pass

        # fallback：FTS5 关键词检索
        if not results:
            # 转义 FTS5 特殊字符（双引号加倍 + 包裹），避免 OperationalError
            escaped = '"' + query.replace('"', '""') + '"'
            try:
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
                    (escaped, k),
                ).fetchall()
                for r in rows:
                    d = dict(r)
                    raw = d.get("content", "")
                    d["content"] = raw[:300] + ("..." if len(raw) > 300 else "")
                    d["tags"] = json.loads(d.pop("tags_json", "[]"))
                    results.append(d)
            except Exception:
                pass

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

    @tool
    def get_note_relations(note_id: str) -> str:
        """
        查询一条笔记的关系图谱：哪些笔记链接了它、它链接了哪些笔记。
        用户问"这条笔记和哪些笔记有关"、"它的前身是什么"、"有哪些矛盾观点"时调用。
        返回 JSON：{ note_id, outgoing: [{to_id, to_title, relation}], incoming: [{from_id, from_title, relation}] }
        """
        outgoing = conn.execute(
            """
            SELECT e.to_id, n.title as to_title, e.relation, e.created_at
            FROM edges e
            JOIN notes n ON n.id = e.to_id
            WHERE e.from_id = ? AND n.deleted_at IS NULL
            ORDER BY e.created_at DESC
            """,
            (note_id,),
        ).fetchall()

        incoming = conn.execute(
            """
            SELECT e.from_id, n.title as from_title, e.relation, e.created_at
            FROM edges e
            JOIN notes n ON n.id = e.from_id
            WHERE e.to_id = ? AND n.deleted_at IS NULL
            ORDER BY e.created_at DESC
            """,
            (note_id,),
        ).fetchall()

        return json.dumps({
            "note_id": note_id,
            "outgoing": [{"to_id": r[0], "to_title": r[1], "relation": r[2], "created_at": r[3]} for r in outgoing],
            "incoming": [{"from_id": r[0], "from_title": r[1], "relation": r[2], "created_at": r[3]} for r in incoming],
        }, ensure_ascii=False)

    @tool
    def suggest_relation(from_id: str, to_id: str, relation: str = "related") -> str:
        """
        建议在两个笔记之间建立关系。适合 LLM 发现两篇笔记存在逻辑关联时调用。
        relation 可选: related / contradicts / evolved_from / supersedes。
        建议的关系需要用户确认后才会变为 confirmed。
        返回 JSON：{ status, suggestion_id }
        """
        valid = {"related", "contradicts", "evolved_from", "supersedes", "similar"}
        if relation not in valid:
            return json.dumps({"status": "error", "message": f"relation 必须是 {valid}"}, ensure_ascii=False)

        # 检查两篇笔记都存在
        for nid in (from_id, to_id):
            row = conn.execute(
                "SELECT id FROM notes WHERE id = ? AND deleted_at IS NULL", (nid,)
            ).fetchone()
            if not row:
                return json.dumps({"status": "error", "message": f"笔记 {nid} 不存在或已删除"}, ensure_ascii=False)

        sid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO pending_suggestions
               (id, from_id, to_id, relation, confidence, evidence, suggestion_type)
               VALUES (?, ?, ?, ?, 0.6, 'LLM suggested', 'relation')""",
            (sid, from_id, to_id, relation),
        )
        conn.commit()
        return json.dumps({"status": "ok", "suggestion_id": sid, "from_id": from_id, "to_id": to_id, "relation": relation}, ensure_ascii=False)

    @tool
    def accept_suggestion(suggestion_id: str) -> str:
        """
        接受一条待确认的建议（关系或标签合并）。
        接受后：关系建议 → 写入 edges 表（confirmed）；标签合并 → 执行合并。
        返回 JSON：{ status, suggestion_id, action }
        """
        row = conn.execute(
            "SELECT * FROM pending_suggestions WHERE id = ? AND status = 'pending'",
            (suggestion_id,),
        ).fetchone()
        if not row:
            return json.dumps({"status": "error", "message": f"建议 {suggestion_id} 不存在或已处理"}, ensure_ascii=False)

        r = dict(row)
        if r["suggestion_type"] == "relation":
            edge_id = str(uuid.uuid4())
            conn.execute(
                """INSERT OR IGNORE INTO edges
                   (id, from_id, to_id, relation, confidence, source, evidence, status)
                   VALUES (?, ?, ?, ?, ?, 'llm', ?, 'confirmed')""",
                (edge_id, r["from_id"], r["to_id"], r["relation"], r["confidence"], r["evidence"]),
            )
            conn.commit()
            conn.execute(
                "UPDATE pending_suggestions SET status='accepted', decided_at=datetime('now','localtime') WHERE id=?",
                (suggestion_id,),
            )
            conn.commit()
            return json.dumps({"status": "ok", "suggestion_id": suggestion_id, "action": "created_edge", "edge_id": edge_id}, ensure_ascii=False)
        else:
            return json.dumps({"status": "error", "message": f"不支持的建议类型: {r['suggestion_type']}"}, ensure_ascii=False)

    @tool
    def reject_suggestion(suggestion_id: str) -> str:
        """
        拒绝一条待确认的建议。
        返回 JSON：{ status, suggestion_id }
        """
        row = conn.execute(
            "SELECT id FROM pending_suggestions WHERE id = ? AND status = 'pending'",
            (suggestion_id,),
        ).fetchone()
        if not row:
            return json.dumps({"status": "error", "message": f"建议 {suggestion_id} 不存在或已处理"}, ensure_ascii=False)

        conn.execute(
            "UPDATE pending_suggestions SET status='rejected', decided_at=datetime('now','localtime') WHERE id=?",
            (suggestion_id,),
        )
        conn.commit()
        return json.dumps({"status": "ok", "suggestion_id": suggestion_id, "action": "rejected"}, ensure_ascii=False)

    return [search_notes, save_note, get_note, archive_note, get_notes_summary, synthesize_notes, get_note_relations, suggest_relation, accept_suggestion, reject_suggestion]
