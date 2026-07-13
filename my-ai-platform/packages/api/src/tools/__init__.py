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

    @tool
    async def detect_collisions(topic: str = "", k: int = 4) -> str:
        """
        发现笔记之间的意外关联（Idea Collision）。
        用户说"帮我发现意外关联"、"这些笔记有什么联系"、"找一下碰撞"时调用。
        分三步：候选对生成（向量+标签+时间）→ LLM 评分 → 入库。
        topic 可选：指定话题范围，不指定则全库扫描。
        返回 JSON：{ collisions: [{note_a, note_b, score, connection, angle}] }
        """
        from src.lib.embeddings import search_similar

        # Phase A: 候选对生成
        candidates: list[dict] = []

        # A1: 向量搜索（如果指定了 topic）
        if topic:
            try:
                hits = await asyncio.wait_for(search_similar(conn, topic, 20), timeout=TOOL_TIMEOUT)
                candidate_ids = [h["note_id"] for h in hits]
            except Exception:
                candidate_ids = []
        else:
            # 取最近 30 条 live 笔记作为候选池
            rows = conn.execute(
                "SELECT id FROM notes WHERE status='live' AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 30"
            ).fetchall()
            candidate_ids = [r["id"] for r in rows]

        if len(candidate_ids) < 2:
            return json.dumps({"collisions": [], "message": "笔记太少（需要至少 2 条）"}, ensure_ascii=False)

        # 生成候选对（tag overlap 筛选）
        placeholders = ",".join("?" * len(candidate_ids))
        notes = conn.execute(
            f"SELECT id, title, content, tags_json, created_at FROM notes WHERE id IN ({placeholders}) AND status='live' AND deleted_at IS NULL",
            candidate_ids,
        ).fetchall()

        note_map = {r["id"]: dict(r) for r in notes}
        seen_pairs: set[str] = set()

        for i, n1 in enumerate(notes):
            d1 = dict(n1)
            tags1 = set(json.loads(d1["tags_json"] or "[]"))
            for j in range(i + 1, len(notes)):
                d2 = dict(notes[j])
                tags2 = set(json.loads(d2["tags_json"] or "[]"))
                # 至少 1 个共同标签，或时间在 3 天内
                from datetime import datetime
                try:
                    t1 = datetime.fromisoformat(d1["created_at"])
                    t2 = datetime.fromisoformat(d2["created_at"])
                    close_time = abs((t1 - t2).days) <= 3
                except Exception:
                    close_time = False

                pair_key = f"{d1['id']}|{d2['id']}"
                if pair_key in seen_pairs:
                    continue
                if tags1 & tags2 or close_time:
                    seen_pairs.add(pair_key)
                    candidates.append({"note_a": d1, "note_b": d2, "tag_overlap": len(tags1 & tags2), "close_time": close_time})

        # 限制候选对数量（优先 tag overlay 多的 + 时间近的）
        candidates.sort(key=lambda c: (-c["tag_overlap"], -c["close_time"]))
        top_candidates = candidates[:k]

        if not top_candidates:
            return json.dumps({"collisions": [], "message": "没找到候选碰撞对"}, ensure_ascii=False)

        # Phase B: LLM 碰撞评分
        from src.agent.providers.deepseek import make_deepseek
        llm = make_deepseek()

        pairs_text = "\n\n".join(
            f"[{idx}] A: {c['note_a']['title']}\n{c['note_a']['content'][:200]}\n"
            f"B: {c['note_b']['title']}\n{c['note_b']['content'][:200]}"
            for idx, c in enumerate(top_candidates)
        )

        prompt = f"""分析以下笔记对是否有意外关联。对每一对评分（1-10）：
- pattern: 表面无关但底层有相似模式
- contradiction: 互相矛盾的观点
- synthesis: 可组合出新想法
- bridge: 弱连接但有趣

{pairs_text}

以 JSON 数组返回（只返回 score >= 5 的）：
[{{"pair_idx": 0, "score": 7, "connection": "一句话描述关联", "angle": "pattern"}}]

只返回 JSON 数组。"""

        collisions = []
        try:
            from langchain_core.messages import HumanMessage
            resp = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=TOOL_TIMEOUT,
            )
            text = resp.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            scored = json.loads(text)
        except Exception:
            scored = []

        # Phase C: 入库（score >= 7）
        for item in scored:
            if item.get("score", 0) >= 7:
                idx = item.get("pair_idx", -1)
                if 0 <= idx < len(top_candidates):
                    c = top_candidates[idx]
                    cid = str(uuid.uuid4())
                    conn.execute(
                        """INSERT OR IGNORE INTO idea_collisions
                           (id, note_a_id, note_b_id, score, connection, angle, detected_by)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (cid, c["note_a"]["id"], c["note_b"]["id"],
                         item["score"], item.get("connection", ""),
                         item.get("angle", "pattern"), "manual"),
                    )
                    conn.commit()
                    collisions.append({
                        "id": cid,
                        "note_a": {"id": c["note_a"]["id"], "title": c["note_a"]["title"]},
                        "note_b": {"id": c["note_b"]["id"], "title": c["note_b"]["title"]},
                        "score": item["score"],
                        "connection": item.get("connection", ""),
                        "angle": item.get("angle", "pattern"),
                    })

        return json.dumps({"collisions": collisions}, ensure_ascii=False)

    @tool
    def suggest_tags(title: str, content: str) -> str:
        """
        根据笔记标题和内容建议 2-4 个标签。适合在用户没有提供标签时调用。
        返回 JSON：{ suggested_tags: [tag1, tag2, ...] }
        此工具不需要 LLM 调用，基于规则 + 关键词匹配。
        """
        text = f"{title} {content}".lower()
        suggested: list[str] = []

        # 关键词 → 标签映射表
        KEYWORD_MAP = {
            "AI": ["ai", "人工智能", "机器学习", "深度学习", "模型", "agent", "llm", "gpt", "claude", "prompt"],
            "产品": ["产品", "设计", "用户体验", "ux", "功能", "需求", "原型"],
            "技术": ["技术", "代码", "编程", "架构", "系统", "实现", "开发"],
            "商业": ["商业", "市场", "增长", "营销", "盈利", "定价", "用户"],
            "写作": ["写作", "笔记", "文章", "创作", "日记", "反思"],
            "学习": ["学习", "阅读", "课程", "理解", "知识", "方法"],
            "心理学": ["心理学", "认知", "情绪", "行为", "思维", "习惯"],
            "效率": ["效率", "时间", "工具", "流程", "自动化", "习惯"],
            "哲学": ["哲学", "意义", "存在", "伦理", "价值观"],
        }

        for tag, keywords in KEYWORD_MAP.items():
            if any(kw in text for kw in keywords):
                suggested.append(tag)

        # 如果匹配不足 2 个，补充通用标签
        if len(suggested) < 2:
            # 基于字数判断
            if len(content) > 500:
                if "深度" not in suggested: suggested.append("深度思考")
            if len(title) > 20:
                if "随笔" not in suggested: suggested.append("随笔")

        suggested = suggested[:4]
        return json.dumps({"suggested_tags": suggested}, ensure_ascii=False)
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

    @tool
    def merge_tags(canonical: str, aliases: str) -> str:
        """
        合并同义标签，将一组别名统一到标准名称。
        canonical: 标准标签名
        aliases: 用逗号分隔的别名标签列表，例如 "AI, ai, 人工智能"
        返回 JSON：{ status, canonical, merged_count }
        """
        alias_list = [a.strip() for a in (aliases or "").split(",") if a.strip()]
        merged = 0
        for alias in alias_list:
            if alias == canonical:
                continue
            tid = str(uuid.uuid4())
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO tag_aliases (id, canonical, alias) VALUES (?, ?, ?)",
                    (tid, canonical, alias),
                )
                conn.commit()
                if conn.execute("SELECT id FROM tag_aliases WHERE id = ?", (tid,)).fetchone():
                    merged += 1
            except Exception:
                pass
        return json.dumps({"status": "ok", "canonical": canonical, "merged_count": merged}, ensure_ascii=False)

    @tool
    def list_tag_aliases() -> str:
        """
        列出所有已建立的标签同义映射。用户问"有哪些标签合并"、"标签别名"时调用。
        返回 JSON：{ aliases: [{canonical, alias}] }
        """
        rows = conn.execute(
            "SELECT canonical, alias FROM tag_aliases ORDER BY canonical, alias"
        ).fetchall()
        return json.dumps({
            "aliases": [{"canonical": r["canonical"], "alias": r["alias"]} for r in rows]
        }, ensure_ascii=False)

    @tool
    async def web_search(query: str, k: int = 3) -> str:
        """
        搜索互联网获取最新信息。当笔记库和自己的知识不足以回答时使用。
        返回 JSON：{ results: [{title, url, snippet}] }
        """
        k = min(k, 5)
        try:
            from duckduckgo_search import DDGS
            results = await asyncio.wait_for(
                asyncio.to_thread(lambda: list(DDGS().text(query, max_results=k))),
                timeout=10,
            )
            return json.dumps({
                "results": [
                    {"title": r.get("title", ""), "url": r.get("href", ""),
                     "snippet": r.get("body", "")[:200]}
                    for r in results
                ]
            }, ensure_ascii=False)
        except asyncio.TimeoutError:
            return json.dumps({"status": "error", "message": "Web 搜索超时，请稍后重试"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Web 搜索失败: {e}"}, ensure_ascii=False)

    @tool
    async def import_webpage(url: str, tags: str = "") -> str:
        """
        将网页 URL 导入为笔记。用户说"把这篇保存下来"、"导入这个链接"时调用。
        tags 用逗号分隔，例如 'AI,研究'。
        自动提取正文、标题，生成内容哈希去重。
        返回 JSON：{ status, note_id, title, word_count }
        """
        import hashlib
        from urllib.parse import urlparse
        import ipaddress
        import socket

        url = url.strip()
        if not url.startswith(("http://", "https://")):
            return json.dumps({"status": "error", "message": "URL must start with http:// or https://"}, ensure_ascii=False)

        # SSRF 防护
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        try:
            resolved = socket.getaddrinfo(hostname, None)
            for _, _, _, _, sockaddr in resolved:
                ip = sockaddr[0]
                try:
                    addr = ipaddress.ip_address(ip)
                    if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_multicast:
                        return json.dumps({"status": "error", "message": f"Blocked internal IP: {ip}"}, ensure_ascii=False)
                except ValueError:
                    pass
        except Exception as e:
            return json.dumps({"status": "error", "message": f"DNS resolution failed: {e}"}, ensure_ascii=False)

        try:
            import trafilatura
            downloaded = await asyncio.wait_for(
                asyncio.to_thread(trafilatura.fetch_url, url),
                timeout=15,
            )
            if not downloaded:
                return json.dumps({"status": "error", "message": "Failed to fetch URL"}, ensure_ascii=False)

            extracted = trafilatura.extract(downloaded, include_comments=False, include_tables=False,
                                             favor_precision=True, output_format="markdown")
            title = trafilatura.extract(downloaded, include_comments=False, output_format="title") or url
            content = extracted or "[无法提取正文]"
        except asyncio.TimeoutError:
            return json.dumps({"status": "error", "message": "Fetch timeout (>15s)"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Extraction failed: {e}"}, ensure_ascii=False)

        if len(content) > 5 * 1024 * 1024:
            return json.dumps({"status": "error", "message": "Content too large (>5MB)"}, ensure_ascii=False)

        note_id = str(uuid.uuid4())
        tags_list = [t.strip() for t in (tags or "").split(",") if t.strip()]

        conn.execute(
            "INSERT INTO notes (id, title, content, tags_json, source_url, source_type, word_count) "
            "VALUES (?, ?, ?, ?, ?, 'web', ?)",
            (note_id, title[:200], content, json.dumps(tags_list, ensure_ascii=False), url, len(content.split())),
        )
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        conn.execute(
            "INSERT INTO source_trace (id, note_id, source_type, source_url, content_hash, fetch_status) "
            "VALUES (?, ?, 'web', ?, ?, 'ok')",
            (str(uuid.uuid4()), note_id, url, content_hash),
        )
        conn.commit()

        # 后台 embedding
        task = asyncio.create_task(_background_embed(conn, note_id, title, content))
        _background_tasks.add(task)
        task.add_done_callback(_task_done_callback)

        return json.dumps({
            "status": "ok", "note_id": note_id, "title": title[:200],
            "word_count": len(content.split()), "source_url": url,
        }, ensure_ascii=False)

    @tool
    def review_note(note_id: str) -> str:
        """
        记录一次复习操作：更新笔记的复习间隔和最后复习时间。
        基于简化版 SM-2 算法：review_count 0→1d, 1→3d, 2→7d, 3→14d, 4→30d, 5+→60d。
        返回 JSON：{ status, next_interval_days }
        """
        row = conn.execute(
            "SELECT id, review_count, review_interval FROM notes WHERE id = ? AND deleted_at IS NULL",
            (note_id,),
        ).fetchone()
        if not row:
            return json.dumps({"status": "error", "message": f"笔记 {note_id} 不存在"}, ensure_ascii=False)

        count = row["review_count"] or 0
        intervals = [1, 3, 7, 14, 30, 60]
        next_interval = intervals[min(count + 1, len(intervals) - 1)]

        conn.execute(
            """UPDATE notes SET
               last_reviewed_at = datetime('now','localtime'),
               review_interval = ?,
               review_count = ?
               WHERE id = ?""",
            (next_interval, count + 1, note_id),
        )
        conn.commit()
        return json.dumps({"status": "ok", "next_interval_days": next_interval, "review_count": count + 1}, ensure_ascii=False)

    @tool
    def get_due_reviews(k: int = 5) -> str:
        """
        返回当前应该复习的笔记列表（到期或逾期）。
        用户问"有哪些笔记待复习"、"我今天该复习什么"时调用。
        返回 JSON：{ due_reviews: [{id, title, interval_days, overdue_days, review_count}] }
        """
        rows = conn.execute(
            """SELECT id, title, review_count, review_interval, last_reviewed_at, created_at
               FROM notes
               WHERE status = 'live' AND deleted_at IS NULL
                 AND last_reviewed_at IS NOT NULL
               ORDER BY
                 CASE WHEN last_reviewed_at IS NOT NULL
                      THEN julianday('now') - julianday(last_reviewed_at) - review_interval
                      ELSE -1
                 END DESC
               LIMIT ?""",
            (min(k, 20),),
        ).fetchall()

        from datetime import date
        today = date.today()
        due: list[dict] = []
        for r in rows:
            if r["last_reviewed_at"]:
                try:
                    last = date.fromisoformat(r["last_reviewed_at"][:10])
                    overdue = (today - last).days - (r["review_interval"] or 1)
                except Exception:
                    overdue = 0
                if overdue >= -1:  # 到期或即将到期
                    due.append({
                        "id": r["id"], "title": r["title"],
                        "review_count": r["review_count"] or 0,
                        "interval_days": r["review_interval"] or 1,
                        "overdue_days": max(0, overdue),
                    })

        due.sort(key=lambda x: -x["overdue_days"])
        return json.dumps({"due_reviews": due[:k]}, ensure_ascii=False)

    @tool
    def suggest_gaps() -> str:
        """
        分析用户笔记库，发现值得探索但尚未涉及的知识缺口。
        用户问"我还有什么没学"、"知识盲区"、"建议探索什么"时调用。
        返回 JSON：{ gaps: [{topic, reason, suggested_start}] }
        """
        # 获取最近 30 条笔记的标签分布
        rows = conn.execute(
            "SELECT title, tags_json FROM notes WHERE status='live' AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 30"
        ).fetchall()
        if len(rows) < 3:
            return json.dumps({"gaps": [], "message": "笔记太少，积累更多后再来探索知识缺口"}, ensure_ascii=False)

        tag_counts: dict[str, int] = {}
        for r in rows:
            for tag in json.loads(r["tags_json"] or "[]"):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])
        gaps = []

        # 基于简单规则检测缺口
        KNOWN_PAIRS = [
            ("技术", "商业", "技术实现与商业变现的平衡"),
            ("产品", "市场", "产品定位与市场验证的关系"),
            ("学习", "输出", "输入和输出的闭环——你可能在大量输入但缺乏输出"),
            ("AI", "伦理", "AI 能力与伦理边界的反思"),
            ("效率", "深度", "效率工具与深度思考的平衡"),
        ]

        existing = {t[0] for t in top_tags}
        for a, b, reason in KNOWN_PAIRS:
            if a in existing and b not in existing:
                gaps.append({"topic": b, "reason": reason,
                             "suggested_start": f"从你的「{a}」笔记出发，思考{b}维度"})

        return json.dumps({"gaps": gaps[:3]}, ensure_ascii=False)

    @tool
    def suggest_writing() -> str:
        """
        检测笔记库中是否有足够积累的话题，建议撰写综述。
        用户问"有什么可以写的"、"帮我写一篇总结"时调用。
        返回 JSON：{ suggestions: [{topic, note_count, note_ids}] }
        """
        rows = conn.execute(
            "SELECT tags_json, id, title FROM notes WHERE status='live' AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 200"
        ).fetchall()

        tag_clusters: dict[str, list[str]] = {}
        for r in rows:
            for tag in json.loads(r["tags_json"] or "[]"):
                tag_clusters.setdefault(tag, []).append(r["id"])

        suggestions = []
        for tag, nids in sorted(tag_clusters.items(), key=lambda x: -len(x[1])):
            if len(nids) >= 5:
                suggestions.append({
                    "topic": tag,
                    "note_count": len(nids),
                    "note_ids": nids[:5],
                    "prompt": f"我在「{tag}」话题上积累了 {len(nids)} 条笔记，帮我综合成一篇长文。",
                })

        return json.dumps({"suggestions": suggestions[:3]}, ensure_ascii=False)

    return [search_notes, save_note, get_note, archive_note, get_notes_summary, synthesize_notes, get_note_relations, detect_collisions, suggest_tags, suggest_relation, accept_suggestion, reject_suggestion, merge_tags, list_tag_aliases, web_search, import_webpage, review_note, get_due_reviews, suggest_gaps, suggest_writing]
