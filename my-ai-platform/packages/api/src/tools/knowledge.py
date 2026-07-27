"""Knowledge intelligence Agent tools."""

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

def build_knowledge_tools(conn: sqlite3.Connection) -> list:
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
                "SELECT id FROM notes WHERE status='live' "
                "AND knowledge_status='canonical' AND deleted_at IS NULL "
                "ORDER BY created_at DESC LIMIT 30"
            ).fetchall()
            candidate_ids = [r["id"] for r in rows]

        if len(candidate_ids) < 2:
            return json.dumps({"collisions": [], "message": "笔记太少（需要至少 2 条）"}, ensure_ascii=False)

        # 生成候选对（tag overlap 筛选）
        placeholders = ",".join("?" * len(candidate_ids))
        notes = conn.execute(
            f"SELECT id, title, content, tags_json, created_at FROM notes "
            f"WHERE id IN ({placeholders}) AND status='live' "
            f"AND knowledge_status='canonical' AND deleted_at IS NULL",
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
    def get_note_relations(note_id: str) -> str:
        """Return incoming and outgoing relationships for a note."""
        outgoing = conn.execute(
            """
            SELECT e.to_id, n.title AS to_title, e.relation, e.created_at
            FROM edges e
            JOIN notes n ON n.id = e.to_id
            WHERE e.from_id = ? AND n.deleted_at IS NULL
            ORDER BY e.created_at DESC
            """,
            (note_id,),
        ).fetchall()
        incoming = conn.execute(
            """
            SELECT e.from_id, n.title AS from_title, e.relation, e.created_at
            FROM edges e
            JOIN notes n ON n.id = e.from_id
            WHERE e.to_id = ? AND n.deleted_at IS NULL
            ORDER BY e.created_at DESC
            """,
            (note_id,),
        ).fetchall()
        return json.dumps({
            "note_id": note_id,
            "outgoing": [
                {"to_id": row[0], "to_title": row[1], "relation": row[2], "created_at": row[3]}
                for row in outgoing
            ],
            "incoming": [
                {"from_id": row[0], "from_title": row[1], "relation": row[2], "created_at": row[3]}
                for row in incoming
            ],
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
        if r["suggestion_type"] == "relation" or r["suggestion_type"] == "contradiction":
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
        elif r["suggestion_type"] == "tag_merge":
            # Accept tag merge: write to tag_aliases
            canonical = r.get("relation", "")
            alias = r.get("evidence", "")
            if canonical and alias:
                tid = str(uuid.uuid4())
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO tag_aliases (id, canonical, alias) VALUES (?, ?, ?)",
                        (tid, canonical, alias),
                    )
                    conn.commit()
                except Exception:
                    pass
            conn.execute(
                "UPDATE pending_suggestions SET status='accepted', decided_at=datetime('now','localtime') WHERE id=?",
                (suggestion_id,),
            )
            conn.commit()
            return json.dumps({"status": "ok", "suggestion_id": suggestion_id, "action": "merged_tags"}, ensure_ascii=False)
        elif r["suggestion_type"] == "tag_suggest":
            # Accept tag suggestion: just mark accepted (tags applied at note level)
            conn.execute(
                "UPDATE pending_suggestions SET status='accepted', decided_at=datetime('now','localtime') WHERE id=?",
                (suggestion_id,),
            )
            conn.commit()
            return json.dumps({"status": "ok", "suggestion_id": suggestion_id, "action": "accepted_tag_suggestion"}, ensure_ascii=False)
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

    return [get_note_relations, detect_collisions, suggest_tags, suggest_relation, accept_suggestion, reject_suggestion, merge_tags, list_tag_aliases]
