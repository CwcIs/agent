"""
Phase 4B — 统一检索排序器（Bayesian + Decay + Graph multi-factor）

final_score =
  semantic_score  * 0.35 +
  keyword_score   * 0.15 +
  graph_score     * 0.20 +
  bayesian_score  * 0.20 +
  recency_score   * 0.10

bayesian_score = (success + α) / (exposure + α + β)
decay = exp(-λ * days_since_last_reinforced)
"""

import math
import sqlite3
import uuid
from datetime import datetime, timezone

# Bayesian prior: α = β = 1 → uniform prior (0.5)
ALPHA = 1.0
BETA = 1.0

# Decay rate: λ controls how fast relevance decays
# λ = 0.01 → half-life ~69 days; λ = 0.05 → half-life ~14 days
LAMBDA = 0.02  # half-life ~35 days

# Scoring weights
W_SEMANTIC = 0.35
W_KEYWORD = 0.15
W_GRAPH = 0.20
W_BAYESIAN = 0.20
W_RECENCY = 0.10


def record_event(conn: sqlite3.Connection, note_id: str, event_type: str,
                 session_id: str = "", source: str = "") -> None:
    """记录一次检索反馈事件，同时更新 note_stats 聚合。"""
    eid = str(uuid.uuid4())
    try:
        conn.execute(
            """INSERT INTO retrieval_events (id, note_id, session_id, event_type, source)
               VALUES (?, ?, ?, ?, ?)""",
            (eid, note_id, session_id, event_type, source),
        )
        conn.commit()
    except Exception:
        return  # 静默失败，不影响主链路

    # 更新 note_stats 聚合
    _upsert_note_stat(conn, note_id, event_type)


def _upsert_note_stat(conn: sqlite3.Connection, note_id: str, event_type: str) -> None:
    """更新 note_stats 的曝光/成功计数和时间戳。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # 确保行存在
    conn.execute(
        "INSERT OR IGNORE INTO note_stats (note_id) VALUES (?)",
        (note_id,),
    )

    if event_type == "shown":
        conn.execute(
            "UPDATE note_stats SET exposure_count = exposure_count + 1, updated_at = ? WHERE note_id = ?",
            (now, note_id),
        )
    elif event_type in ("cited", "clicked", "accepted", "saved_from"):
        conn.execute(
            """UPDATE note_stats SET
                 success_count = success_count + 1,
                 exposure_count = exposure_count + 1,
                 last_accessed_at = ?,
                 last_reinforced_at = ?,
                 updated_at = ?
               WHERE note_id = ?""",
            (now, now, now, note_id),
        )
    elif event_type == "rejected":
        conn.execute(
            "UPDATE note_stats SET exposure_count = exposure_count + 1, updated_at = ? WHERE note_id = ?",
            (now, note_id),
        )
    conn.commit()


def get_stats(conn: sqlite3.Connection, note_id: str) -> dict:
    """获取单条笔记的统计信息。"""
    row = conn.execute(
        "SELECT * FROM note_stats WHERE note_id = ?", (note_id,)
    ).fetchone()
    if not row:
        return {"exposure_count": 0, "success_count": 0,
                "last_accessed_at": None, "last_reinforced_at": None}
    return dict(row)


def bayesian_score(stats: dict) -> float:
    """计算 Bayesian 有效性分数。默认 0.5（无数据时）。"""
    exposure = stats.get("exposure_count", 0)
    success = stats.get("success_count", 0)
    return (success + ALPHA) / (exposure + ALPHA + BETA)


def recency_score(last_reinforced_at: str | None) -> float:
    """计算时间衰减分数。从未被引用过 → 统一返回 0.5（中性）。"""
    if not last_reinforced_at:
        return 0.5
    try:
        last = datetime.fromisoformat(last_reinforced_at)
        now = datetime.now(timezone.utc)
        days = (now - last.replace(tzinfo=timezone.utc)).days
        return math.exp(-LAMBDA * max(days, 0))
    except Exception:
        return 0.5


def graph_score(conn: sqlite3.Connection, note_id: str) -> float:
    """根据笔记的关系网络密度计算图谱分数。连接数越多 → 分数越高。"""
    count = conn.execute(
        "SELECT COUNT(*) FROM edges WHERE (from_id = ? OR to_id = ?) AND status = 'confirmed'",
        (note_id, note_id),
    ).fetchone()[0]
    # 使用对数缩放：0 连接 → 0.3, 1-2 → 0.5, 3-5 → 0.7, 6+ → 0.9
    if count == 0:
        return 0.3
    return min(0.3 + 0.1 * math.log(count + 1) * 3, 0.95)


def rank_candidates(
    conn: sqlite3.Connection,
    candidates: list[dict],
    semantic_scores: dict[str, float] | None = None,
    keyword_scores: dict[str, float] | None = None,
) -> list[dict]:
    """
    对候选笔记进行多因子排序。

    candidates: [{note_id, title, content, ...}] — 每个 dict 至少含 note_id
    semantic_scores: {note_id: float} — 0-1 的语义相似度（由调用方传入）
    keyword_scores: {note_id: float} — 0-1 的关键词匹配分

    返回带 _ranker 字段的排序后列表。
    """
    scored: list[dict] = []
    now = datetime.now(timezone.utc)

    for c in candidates:
        nid = c.get("note_id", c.get("id", ""))
        sem = (semantic_scores or {}).get(nid, 0.5)
        kw = (keyword_scores or {}).get(nid, 0.5)

        stats = get_stats(conn, nid)
        bayes = bayesian_score(stats)
        graph = graph_score(conn, nid)
        recency = recency_score(stats.get("last_reinforced_at"))

        final = round(
            sem * W_SEMANTIC +
            kw * W_KEYWORD +
            graph * W_GRAPH +
            bayes * W_BAYESIAN +
            recency * W_RECENCY,
            4,
        )

        scored.append({
            **c,
            "_ranker": {
                "semantic_score": round(sem, 3),
                "keyword_score": round(kw, 3),
                "graph_score": round(graph, 3),
                "bayesian_score": round(bayes, 3),
                "recency_score": round(recency, 3),
                "final_score": final,
                "exposure": stats.get("exposure_count", 0),
                "success": stats.get("success_count", 0),
            },
        })

    scored.sort(key=lambda x: x["_ranker"]["final_score"], reverse=True)
    return scored
