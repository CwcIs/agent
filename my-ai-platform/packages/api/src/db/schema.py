# ============================================================
# SQLite 8 表 Schema（Phase 1 + 2 + 3）
# 对应 MD §8.5 Phase 1 全部表 + §4.3 数据模型
#
# 表：
#   1. notes           — 笔记主表（status / superseded_by / deleted_at）
#   2. messages        — 对话消息（session_id / agent_id / prompt_version）
#   3. daily_digests   — 每日 AI 回顾（惰性触发 + 缓存）
#   4. llm_calls       — LLM 调用审计（计费 + 重试 + 排查）
#   5. llm_errors      — JSON 解析 / tool_use 失败记录
#   6. eval_runs       — 黄金集运行记录
#   7. embedding_meta  — embedding 模型指纹（换模型只加一行）
#   8. worklist        — A2A 任务持久化（进程崩了不丢 handoff）
#
# 为什么这 6 张？（MD §8.5）：
#   notes / messages 是业务，剩下 4 张全是工程兜底。
#   没有它们就只能"感觉"AI 在变好，没法量化。
#   Phase 1 就要把"可观测"扎进 schema，不等 Phase 3 才补。
#
# 为什么 embedding 拆出去？（MD §4.3）：
#   Phase 2 换 embedding 模型时，向量塞在 notes 里要全表回填。
#   拆成独立表 + embedding_meta 指纹，换模型时新增一行 meta、
#   后台慢慢回算，老向量继续服务旧查询。
# ============================================================

import sqlite3
import sqlite_vec
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "app.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")  # 5s timeout to avoid "database is locked" under concurrent writes
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""

        -- ① notes 笔记主表
        CREATE TABLE IF NOT EXISTS notes (
            id             TEXT PRIMARY KEY,
            title          TEXT NOT NULL,
            content        TEXT NOT NULL,
            summary        TEXT NOT NULL DEFAULT '',
            tags_json      TEXT NOT NULL DEFAULT '[]',
            source         TEXT NOT NULL DEFAULT '',
            status         TEXT NOT NULL DEFAULT 'live'
                               CHECK(status IN ('live','superseded','archived')),
            superseded_by  TEXT REFERENCES notes(id),
            confidence     REAL,
            schema_version INTEGER NOT NULL DEFAULT 1,
            created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            deleted_at     TEXT
        );

        -- FTS5 全文检索（title + content 两列）
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
            title, content,
            content='notes', content_rowid='rowid'
        );

        -- FTS5 自动同步触发器（insert / update / delete）
        CREATE TRIGGER IF NOT EXISTS notes_fts_insert AFTER INSERT ON notes BEGIN
            INSERT INTO notes_fts(rowid, title, content)
            VALUES (new.rowid, new.title, new.content);
        END;
        CREATE TRIGGER IF NOT EXISTS notes_fts_update AFTER UPDATE ON notes BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, title, content)
            VALUES ('delete', old.rowid, old.title, old.content);
            INSERT INTO notes_fts(rowid, title, content)
            VALUES (new.rowid, new.title, new.content);
        END;
        CREATE TRIGGER IF NOT EXISTS notes_fts_delete AFTER DELETE ON notes BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, title, content)
            VALUES ('delete', old.rowid, old.title, old.content);
        END;

        -- ② messages 对话消息
        CREATE TABLE IF NOT EXISTS messages (
            id             TEXT PRIMARY KEY,
            session_id     TEXT NOT NULL,
            agent_id       TEXT NOT NULL DEFAULT 'claude',
            role           TEXT NOT NULL CHECK(role IN ('user','assistant','tool')),
            content        TEXT NOT NULL,
            tool_call_id   TEXT,
            prompt_version TEXT NOT NULL DEFAULT 'v1',
            created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id, created_at);

        -- ③ daily_digests 每日 AI 回顾
        CREATE TABLE IF NOT EXISTS daily_digests (
            id           TEXT PRIMARY KEY,
            date         TEXT NOT NULL UNIQUE,
            note_count   INTEGER NOT NULL DEFAULT 0,
            narrative    TEXT NOT NULL DEFAULT '',
            follow_ups   TEXT NOT NULL DEFAULT '[]',
            cited_notes  TEXT NOT NULL DEFAULT '[]',
            created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- ④ llm_calls LLM 调用审计
        CREATE TABLE IF NOT EXISTS llm_calls (
            id             TEXT PRIMARY KEY,
            session_id     TEXT NOT NULL,
            prompt_version TEXT NOT NULL DEFAULT 'v1',
            model          TEXT NOT NULL,
            input_tokens   INTEGER NOT NULL DEFAULT 0,
            output_tokens  INTEGER NOT NULL DEFAULT 0,
            cost_usd       REAL NOT NULL DEFAULT 0.0,
            latency_ms     INTEGER NOT NULL DEFAULT 0,
            status         TEXT NOT NULL DEFAULT 'ok'
                               CHECK(status IN ('ok','error','retry')),
            created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_llm_calls_session
            ON llm_calls(session_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_llm_calls_date
            ON llm_calls(created_at);

        -- ⑤ llm_errors JSON 解析 / tool_use 失败记录
        CREATE TABLE IF NOT EXISTS llm_errors (
            id           TEXT PRIMARY KEY,
            session_id   TEXT NOT NULL,
            llm_call_id  TEXT REFERENCES llm_calls(id),
            error_type   TEXT NOT NULL,
            raw_output   TEXT,
            error_msg    TEXT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- ⑥ eval_runs 黄金集运行记录
        CREATE TABLE IF NOT EXISTS eval_runs (
            id             TEXT PRIMARY KEY,
            prompt_version TEXT NOT NULL DEFAULT 'v1',
            total          INTEGER NOT NULL DEFAULT 0,
            passed         INTEGER NOT NULL DEFAULT 0,
            failed         INTEGER NOT NULL DEFAULT 0,
            pass_rate      REAL NOT NULL DEFAULT 0.0,
            details        TEXT NOT NULL DEFAULT '[]',
            created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- ⑦ embedding_meta — embedding 模型指纹，换模型时只加一行
        CREATE TABLE IF NOT EXISTS embedding_meta (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id   TEXT NOT NULL,
            dim        INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- ⑧ worklist — A2A 任务持久化（进程崩了不丢 handoff）
        CREATE TABLE IF NOT EXISTS worklist (
            id              TEXT PRIMARY KEY,
            session_id      TEXT NOT NULL,
            agent_id        TEXT NOT NULL,
            depth           INTEGER NOT NULL DEFAULT 0,
            status          TEXT NOT NULL DEFAULT 'pending'
                                CHECK(status IN ('pending','running','done','failed')),
            user_input      TEXT NOT NULL,
            agent_a_output  TEXT NOT NULL DEFAULT '',
            mention_content TEXT NOT NULL DEFAULT '',
            tool_events_json TEXT NOT NULL DEFAULT '[]',
            error_msg       TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_worklist_session
            ON worklist(session_id, status);

    """)

    # ── 迁移：Phase 4 daily_digests 增加 trends / anomalies 列 ──
    for col in ("trends", "anomalies"):
        try:
            conn.execute(f"ALTER TABLE daily_digests ADD COLUMN {col} TEXT NOT NULL DEFAULT '[]'")
        except Exception:
            pass  # 列已存在

    conn.commit()
