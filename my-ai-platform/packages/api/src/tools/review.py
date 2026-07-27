"""Review and proactive intelligence Agent tools."""

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

def build_review_tools(conn: sqlite3.Connection) -> list:
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
               WHERE status = 'live' AND knowledge_status='canonical'
                 AND deleted_at IS NULL
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
    async def suggest_gaps() -> str:
        """
        分析用户笔记库，发现值得探索但尚未涉及的知识缺口。
        使用 LLM 分析话题覆盖和缺失维度。
        用户问"我还有什么没学"、"知识盲区"、"建议探索什么"时调用。
        返回 JSON：{ gaps: [{topic, reason, suggested_start}] }
        """
        # 获取最近 50 条笔记作为分析样本
        rows = conn.execute(
            "SELECT title, content, tags_json FROM notes WHERE status='live' "
            "AND knowledge_status='canonical' AND deleted_at IS NULL "
            "ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        if len(rows) < 3:
            return json.dumps({"gaps": [], "message": "笔记太少，积累更多后再来探索知识缺口"}, ensure_ascii=False)

        notes_text = "\n".join(
            f"- 标题：{dict(r)['title']} | 标签：{json.loads(dict(r)['tags_json'] or '[]')} | 内容摘要：{dict(r)['content'][:100]}"
            for r in rows
        )

        prompt = f"""分析以下用户的笔记，找出 1-3 个值得探索但尚未深入的知识缺口。

用户笔记样本：
{notes_text}

要求：
1. 找出用户已覆盖的话题，然后思考相邻但缺失的维度
2. 每个缺口说明：为什么重要，可以从哪里开始了解
3. 如果用户笔记覆盖比较全面，可以少返回或不返回

以 JSON 数组返回：
[{{"topic": "缺口话题", "reason": "为什么这个缺口值得填补", "suggested_start": "建议从哪开始"}}]

只返回 JSON 数组。"""

        from src.agent.providers.deepseek import make_deepseek
        llm = make_deepseek()
        try:
            from langchain_core.messages import HumanMessage
            resp = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=TOOL_TIMEOUT,
            )
            text = resp.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            gaps = json.loads(text)
        except asyncio.TimeoutError:
            return json.dumps({"gaps": [], "message": "LLM 调用超时，请稍后重试"}, ensure_ascii=False)
        except Exception:
            # fallback to rule-based
            tag_counts: dict[str, int] = {}
            for r in rows:
                for tag in json.loads(dict(r)["tags_json"] or "[]"):
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

            top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])
            existing = {t[0] for t in top_tags}
            gaps = []
            KNOWN_PAIRS = [
                ("技术", "商业", "技术实现与商业变现的平衡"),
                ("产品", "市场", "产品定位与市场验证的关系"),
                ("学习", "输出", "输入和输出的闭环——你可能在大量输入但缺乏输出"),
                ("AI", "伦理", "AI 能力与伦理边界的反思"),
                ("效率", "深度", "效率工具与深度思考的平衡"),
            ]
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
            "SELECT tags_json, id, title FROM notes WHERE status='live' "
            "AND knowledge_status='canonical' AND deleted_at IS NULL "
            "ORDER BY created_at DESC LIMIT 200"
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

    # ── Phase 7.2: Calendar tools ──

    return [review_note, get_due_reviews, suggest_gaps, suggest_writing]
