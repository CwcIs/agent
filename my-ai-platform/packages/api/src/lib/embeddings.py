"""
向量化工具 — Phase 2
使用 sentence-transformers 本地模型，离线可用，无需 API key。
模型：paraphrase-multilingual-MiniLM-L12-v2（中英双语，384 维）

方案 B：embed() 通过 run_in_executor() 跑在线程池，
不阻塞 FastAPI event loop，解决 SSE 流式输出卡顿问题。
"""

import asyncio
import concurrent.futures
import json
import sqlite3
import struct
from functools import lru_cache, partial
from typing import List

MODEL_ID = "paraphrase-multilingual-MiniLM-L12-v2"
DIM = 384

# 线程池：专用于 CPU-bound 的 encode 计算
# max_workers=2 足够（PyTorch 内部已有并行），避免过多线程争 GIL
_embed_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_ID)


async def embed(text: str) -> List[float]:
    """异步向量化：把 CPU 密集的 encode 丢到线程池，不阻塞 event loop。"""
    model = _get_model()
    loop = asyncio.get_running_loop()
    func = partial(model.encode, text, normalize_embeddings=True)
    vec = await loop.run_in_executor(_embed_executor, func)
    return vec.tolist()


def serialize(vec: List[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def ensure_vec_table(conn: sqlite3.Connection) -> None:
    """建 note_embeddings 虚拟表（幂等）并注册 embedding_meta。"""
    conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS note_embeddings
        USING vec0(
            note_id TEXT PRIMARY KEY,
            embedding float[{DIM}]
        )
    """)
    # 记录当前使用的 embedding 模型（如已记录则跳过）
    exists = conn.execute(
        "SELECT 1 FROM embedding_meta WHERE model_id = ? AND dim = ?",
        (MODEL_ID, DIM),
    ).fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO embedding_meta (model_id, dim) VALUES (?, ?)",
            (MODEL_ID, DIM),
        )
    conn.commit()


async def upsert_embedding(conn: sqlite3.Connection, note_id: str, text: str) -> None:
    """为一条笔记计算并存入向量（title + content 拼接）。"""
    ensure_vec_table(conn)
    vec = await embed(text)
    conn.execute("DELETE FROM note_embeddings WHERE note_id = ?", (note_id,))
    conn.execute(
        "INSERT INTO note_embeddings(note_id, embedding) VALUES (?, ?)",
        (note_id, serialize(vec)),
    )
    conn.commit()


async def search_similar(conn: sqlite3.Connection, query: str, k: int = 5) -> list[dict]:
    """向量相似度搜索，返回最近 k 条笔记的 id + distance。"""
    ensure_vec_table(conn)
    vec = await embed(query)
    rows = conn.execute(
        f"""
        SELECT note_id, distance
        FROM note_embeddings
        WHERE embedding MATCH ?
          AND k = ?
        ORDER BY distance
        """,
        (serialize(vec), k),
    ).fetchall()
    return [{"note_id": r[0], "distance": r[1]} for r in rows]
