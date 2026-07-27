# ============================================================
# SQLite Schema（知识工作台 + Governance Gate v2）
#
# 表：
#   1. notes           — 笔记主表（Phase 5.3: +source_url/source_file/source_type/word_count）
#   2. messages        — 对话消息
#   3. daily_digests   — 每日 AI 回顾
#   4. llm_calls       — LLM 调用审计
#   5. llm_errors      — JSON 解析 / tool_use 失败
#   6. eval_runs       — 黄金集运行记录
#   7. embedding_meta  — embedding 模型指纹
#   8. edges           — 笔记关系图谱
#   9. worklist        — A2A 任务持久化
#  10. pending_suggestions — 待确认的关系/标签建议
#  11. idea_collisions — 意外关联发现
#  12. tag_aliases     — 标签同义词
#  13. retrieval_events— 检索反馈事件
#  14. note_stats      — 笔记排序统计
#  15. source_trace    — 外部来源追踪（Phase 5.3）
#  16. custom_tools    — 用户自定义 HTTP 工具
#  17. trace_events    — 全链路、可校验执行事件账本
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
            knowledge_status TEXT NOT NULL DEFAULT 'canonical'
                               CHECK(knowledge_status IN (
                                   'draft','pending_review','canonical',
                                   'superseded','revoked','expired'
                               )),
            proposed_supersedes_id TEXT,
            origin_session_id TEXT NOT NULL DEFAULT '',
            reviewed_by    TEXT NOT NULL DEFAULT '',
            reviewed_at    TEXT,
            published_at   TEXT,
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

        -- ⑧ edges — 笔记关系图谱（wikilink / evolved_from / supersedes / contradicts / similar / related）
        CREATE TABLE IF NOT EXISTS edges (
            id         TEXT PRIMARY KEY,
            from_id    TEXT NOT NULL REFERENCES notes(id),
            to_id      TEXT NOT NULL REFERENCES notes(id),
            relation   TEXT NOT NULL CHECK(relation IN ('wikilink','evolved_from','supersedes','contradicts','similar','related')),
            confidence REAL NOT NULL DEFAULT 1.0,
            source     TEXT NOT NULL DEFAULT 'manual'
                           CHECK(source IN ('manual','wikilink','embedding','llm','system')),
            evidence   TEXT NOT NULL DEFAULT '',
            status     TEXT NOT NULL DEFAULT 'confirmed'
                           CHECK(status IN ('confirmed','suggested','rejected')),
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE(from_id, to_id, relation)
        );
        CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id);
        CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id);

        -- ⑩ pending_suggestions — 待确认的关系/标签建议
        CREATE TABLE IF NOT EXISTS pending_suggestions (
            id         TEXT PRIMARY KEY,
            from_id    TEXT NOT NULL REFERENCES notes(id),
            to_id      TEXT REFERENCES notes(id),
            relation   TEXT NOT NULL DEFAULT 'related',
            confidence REAL NOT NULL DEFAULT 0.5,
            evidence   TEXT NOT NULL DEFAULT '',
            suggestion_type TEXT NOT NULL DEFAULT 'relation'
                              CHECK(suggestion_type IN ('relation','tag_merge','tag_suggest','contradiction')),
            status     TEXT NOT NULL DEFAULT 'pending'
                           CHECK(status IN ('pending','accepted','rejected')),
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            decided_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_pending_suggestions_status ON pending_suggestions(status);

        -- ⑪ idea_collisions — 意外关联发现（Phase 4.3）
        CREATE TABLE IF NOT EXISTS idea_collisions (
            id          TEXT PRIMARY KEY,
            note_a_id   TEXT NOT NULL REFERENCES notes(id),
            note_b_id   TEXT NOT NULL REFERENCES notes(id),
            score       INTEGER NOT NULL DEFAULT 0 CHECK(score BETWEEN 1 AND 10),
            connection  TEXT NOT NULL DEFAULT '',
            angle       TEXT NOT NULL DEFAULT 'pattern'
                            CHECK(angle IN ('pattern','contradiction','synthesis','bridge')),
            is_read     INTEGER NOT NULL DEFAULT 0,
            detected_by TEXT NOT NULL DEFAULT 'manual'
                            CHECK(detected_by IN ('manual','daily_digest','save_note')),
            created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_idea_collisions_read ON idea_collisions(is_read);

        -- ⑫ tag_aliases — 标签同义词（Phase 4.4）
        CREATE TABLE IF NOT EXISTS tag_aliases (
            id         TEXT PRIMARY KEY,
            canonical  TEXT NOT NULL,
            alias      TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_tag_aliases_canonical ON tag_aliases(canonical);

        -- ⑬ retrieval_events — 检索反馈事件（Phase 4B）
        CREATE TABLE IF NOT EXISTS retrieval_events (
            id         TEXT PRIMARY KEY,
            note_id    TEXT NOT NULL REFERENCES notes(id),
            session_id TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL CHECK(event_type IN ('shown','cited','clicked','accepted','rejected','saved_from')),
            source     TEXT NOT NULL DEFAULT ''
                           CHECK(source IN ('search','context','digest','graph','manual','')),
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_retrieval_events_note ON retrieval_events(note_id, event_type);

        -- ⑭ note_stats — 笔记排序统计（Phase 4B）
        CREATE TABLE IF NOT EXISTS note_stats (
            note_id              TEXT PRIMARY KEY REFERENCES notes(id),
            exposure_count       INTEGER NOT NULL DEFAULT 0,
            success_count        INTEGER NOT NULL DEFAULT 0,
            last_accessed_at     TEXT,
            last_reinforced_at   TEXT,
            created_at           TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at           TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- ⑮ source_trace — 外部来源追踪（Phase 5.3）
        CREATE TABLE IF NOT EXISTS source_trace (
            id          TEXT PRIMARY KEY,
            note_id     TEXT NOT NULL REFERENCES notes(id),
            source_type TEXT NOT NULL CHECK(source_type IN ('web','file','user','agent_generated')),
            source_url  TEXT NOT NULL DEFAULT '',
            source_file TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL DEFAULT '',
            fetch_status TEXT NOT NULL DEFAULT 'ok'
                             CHECK(fetch_status IN ('ok','partial','failed')),
            imported_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_source_trace_note ON source_trace(note_id);

        -- ⑰ trace_events — 根 trace 下的全链路事件账本
        CREATE TABLE IF NOT EXISTS trace_events (
            id              TEXT PRIMARY KEY,
            trace_id        TEXT NOT NULL,
            phase_trace_id  TEXT NOT NULL DEFAULT '',
            session_id      TEXT NOT NULL DEFAULT '',
            sequence        INTEGER NOT NULL,
            event_type      TEXT NOT NULL,
            agent_id        TEXT NOT NULL DEFAULT '',
            parent_agent_id TEXT NOT NULL DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'ok',
            name            TEXT NOT NULL DEFAULT '',
            payload_json    TEXT NOT NULL DEFAULT '{}',
            prev_hash       TEXT NOT NULL DEFAULT '',
            event_hash      TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now','localtime')),
            UNIQUE(trace_id, sequence)
        );
        CREATE INDEX IF NOT EXISTS idx_trace_events_root
            ON trace_events(trace_id, sequence);
        CREATE INDEX IF NOT EXISTS idx_trace_events_phase
            ON trace_events(phase_trace_id, sequence);
        CREATE INDEX IF NOT EXISTS idx_trace_events_session
            ON trace_events(session_id, created_at);

        -- ⑯ custom_tools — 用户自定义 HTTP 工具（Phase 7.3）
        CREATE TABLE IF NOT EXISTS custom_tools (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL UNIQUE,
            description     TEXT NOT NULL DEFAULT '',
            endpoint        TEXT NOT NULL,
            method          TEXT NOT NULL DEFAULT 'GET'
                                CHECK(method IN ('GET','POST')),
            params_json     TEXT NOT NULL DEFAULT '{}',
            headers_json    TEXT NOT NULL DEFAULT '{}',
            output_template TEXT NOT NULL DEFAULT '{{response}}',
            enabled         INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- ⑨ worklist — A2A 任务持久化（进程崩了不丢 handoff）
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
            agent_a_id      TEXT NOT NULL DEFAULT '',
            error_msg       TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_worklist_session
            ON worklist(session_id, status);

        -- Governance G2：mention 只创建 proposal，不直接代表执行授权
        CREATE TABLE IF NOT EXISTS handoff_proposals (
            id                          TEXT PRIMARY KEY,
            trace_id                    TEXT NOT NULL DEFAULT '',
            phase_trace_id              TEXT NOT NULL DEFAULT '',
            session_id                  TEXT NOT NULL,
            source_agent_id             TEXT NOT NULL,
            target_agent_id             TEXT NOT NULL,
            objective                   TEXT NOT NULL DEFAULT '',
            data_sensitivity            TEXT NOT NULL DEFAULT 'normal'
                                           CHECK(data_sensitivity IN ('normal','sensitive')),
            input_refs_json             TEXT NOT NULL DEFAULT '[]',
            requested_capabilities_json TEXT NOT NULL DEFAULT '[]',
            trigger_type                TEXT NOT NULL DEFAULT 'explicit'
                                           CHECK(trigger_type IN ('explicit','shadow')),
            depth                       INTEGER NOT NULL DEFAULT 0,
            proposal_hash               TEXT NOT NULL,
            status                      TEXT NOT NULL DEFAULT 'proposed'
                                           CHECK(status IN (
                                               'proposed','allow','ask_user',
                                               'degrade','deny','executed','expired'
                                           )),
            policy_version              TEXT NOT NULL DEFAULT '',
            decision_reason             TEXT NOT NULL DEFAULT '',
            created_at                  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at                  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_handoff_proposals_trace
            ON handoff_proposals(trace_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_handoff_proposals_session
            ON handoff_proposals(session_id, status);

        -- Governance Policy Plane：保留每次确定性策略判断
        CREATE TABLE IF NOT EXISTS policy_decisions (
            id              TEXT PRIMARY KEY,
            proposal_id     TEXT NOT NULL REFERENCES handoff_proposals(id),
            policy_version  TEXT NOT NULL,
            outcome         TEXT NOT NULL
                                CHECK(outcome IN ('allow','ask_user','degrade','deny')),
            effective_risk  TEXT NOT NULL CHECK(effective_risk IN ('R0','R1','R2','R3')),
            reason          TEXT NOT NULL,
            dimensions_json TEXT NOT NULL DEFAULT '{}',
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_policy_decisions_proposal
            ON policy_decisions(proposal_id, created_at);

        -- Governance Execution Plane：审批绑定、幂等键与真实执行结果
        CREATE TABLE IF NOT EXISTS execution_ledger (
            id              TEXT PRIMARY KEY,
            proposal_id     TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL UNIQUE,
            action_type     TEXT NOT NULL,
            actor_id        TEXT NOT NULL DEFAULT 'orchestrator',
            request_hash    TEXT NOT NULL,
            request_json    TEXT NOT NULL DEFAULT '{}',
            status          TEXT NOT NULL DEFAULT 'pending'
                                CHECK(status IN (
                                    'pending','running','succeeded',
                                    'failed','compensated'
                                )),
            result_json     TEXT NOT NULL DEFAULT '{}',
            error_msg       TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            started_at      TEXT,
            completed_at    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_execution_ledger_proposal
            ON execution_ledger(proposal_id, created_at);

    """)

    # ── 迁移：Phase 4 daily_digests 增加 trends / anomalies 列 ──
    for col in ("trends", "anomalies"):
        try:
            conn.execute(f"ALTER TABLE daily_digests ADD COLUMN {col} TEXT NOT NULL DEFAULT '[]'")
        except Exception:
            pass  # 列已存在

    # ── 迁移：worklist 增加 agent_a_id 列（package_handoff 动态 header） ──
    try:
        conn.execute("ALTER TABLE worklist ADD COLUMN agent_a_id TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass  # 列已存在

    # ── 迁移：llm_calls 增加 trace_id 列（Trace 面板） ──
    try:
        conn.execute("ALTER TABLE llm_calls ADD COLUMN trace_id TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_trace ON llm_calls(trace_id)")
    except Exception:
        pass  # 列已存在

    # ── 迁移：llm_calls 增加 agent_id 列（Trace 面板按 Agent 分组） ──
    try:
        conn.execute("ALTER TABLE llm_calls ADD COLUMN agent_id TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass  # 列已存在

    for col, definition in [
        ("proposal_id", "TEXT NOT NULL DEFAULT ''"),
        ("idempotency_key", "TEXT NOT NULL DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE worklist ADD COLUMN {col} {definition}")
        except Exception:
            pass
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_worklist_idempotency "
        "ON worklist(idempotency_key) WHERE idempotency_key != ''"
    )

    try:
        conn.execute(
            "ALTER TABLE handoff_proposals "
            "ADD COLUMN trigger_type TEXT NOT NULL DEFAULT 'explicit'"
        )
    except Exception:
        pass
    try:
        conn.execute(
            "ALTER TABLE handoff_proposals "
            "ADD COLUMN data_sensitivity TEXT NOT NULL DEFAULT 'normal'"
        )
    except Exception:
        pass

    # ── 迁移：retrieval_events 关联根 trace 与 Agent phase ──
    for column in ("trace_id", "phase_trace_id"):
        try:
            conn.execute(
                f"ALTER TABLE retrieval_events ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
            )
        except Exception:
            pass
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_retrieval_events_trace "
        "ON retrieval_events(trace_id, created_at)"
    )

    # ── 迁移（Phase 4A-1）：edges 增加 confidence / source / evidence / status 列 ──
    for col, default, col_type in [
        ("confidence", "1.0", "REAL"),
        ("source", "'manual'", "TEXT"),
        ("evidence", "''", "TEXT"),
        ("status", "'confirmed'", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE edges ADD COLUMN {col} {col_type} NOT NULL DEFAULT {default}")
        except Exception:
            pass  # 列已存在

    conn.commit()

    # ── 迁移（Phase 6.3）：notes 增加复习间隔列 ──
    for col, default, col_type in [
        ("last_reviewed_at", "NULL", "TEXT"),
        ("review_interval", "1", "INTEGER"),
        ("review_count", "0", "INTEGER"),
    ]:
        try:
            conn.execute(f"ALTER TABLE notes ADD COLUMN {col} {col_type} DEFAULT {default}")
        except Exception:
            pass

    # ── 迁移（Phase 5.3）：notes 增加 source_url/source_file/source_type/word_count ──
    for col, default, col_type in [
        ("source_url", "''", "TEXT"),
        ("source_file", "''", "TEXT"),
        ("source_type", "'user'", "TEXT"),
        ("word_count", "0", "INTEGER"),
    ]:
        try:
            conn.execute(f"ALTER TABLE notes ADD COLUMN {col} {col_type} NOT NULL DEFAULT {default}")
        except Exception:
            pass  # 列已存在

    # ── 迁移（Phase 7.4）：notes 增加 attachments_json ──
    try:
        conn.execute("ALTER TABLE notes ADD COLUMN attachments_json TEXT NOT NULL DEFAULT '[]'")
    except Exception:
        pass

    # ── 迁移（Gate v2 G4）：候选知识与 canonical RAG 隔离 ──
    for col, definition in [
        ("knowledge_status", "TEXT NOT NULL DEFAULT 'canonical'"),
        ("proposed_supersedes_id", "TEXT"),
        ("origin_session_id", "TEXT NOT NULL DEFAULT ''"),
        ("reviewed_by", "TEXT NOT NULL DEFAULT ''"),
        ("reviewed_at", "TEXT"),
        ("published_at", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE notes ADD COLUMN {col} {definition}")
        except Exception:
            pass
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notes_knowledge_status "
        "ON notes(knowledge_status, status, created_at)"
    )

    conn.commit()
