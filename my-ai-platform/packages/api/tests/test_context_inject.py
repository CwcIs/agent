"""Smoke test for related notes injection in assemble_context()."""
import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from context.assemble import assemble_context, _fetch_related_notes


def test_fetch_related_notes_finds_match():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE notes (id TEXT, title TEXT, content TEXT, status TEXT DEFAULT 'live', "
        "deleted_at TEXT, tags_json TEXT DEFAULT '[]', created_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        'CREATE VIRTUAL TABLE notes_fts USING fts5(title, content, content="notes", content_rowid="rowid")'
    )
    conn.execute(
        "CREATE TRIGGER notes_fts_insert AFTER INSERT ON notes BEGIN "
        "INSERT INTO notes_fts(rowid, title, content) VALUES (new.rowid, new.title, new.content); END"
    )
    conn.execute(
        "CREATE TABLE messages (id TEXT, session_id TEXT, agent_id TEXT DEFAULT 'knowledge', "
        "role TEXT, content TEXT, created_at TEXT)"
    )
    conn.commit()

    # Use ASCII content to avoid encoding issues in test harness
    conn.execute(
        "INSERT INTO notes (id, title, content) VALUES ('n1', 'Knowledge Graph Design', 'thinking about graphs...')"
    )
    conn.execute(
        "INSERT INTO notes (id, title, content) VALUES ('n2', 'Context Refactor', 'context assembly needs work...')"
    )
    conn.commit()

    # Search should match
    result = _fetch_related_notes(conn, "knowledge graph")
    assert "Knowledge Graph Design" in result, f"Expected match, got: {result}"
    assert "相关" in result  # Chinese header
    print("PASS test_fetch_related_notes_finds_match")


def test_fetch_related_notes_no_match():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE notes (id TEXT, title TEXT, content TEXT, status TEXT DEFAULT 'live', "
        "deleted_at TEXT, tags_json TEXT DEFAULT '[]', created_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        'CREATE VIRTUAL TABLE notes_fts USING fts5(title, content, content="notes", content_rowid="rowid")'
    )
    conn.execute(
        "CREATE TRIGGER notes_fts_insert AFTER INSERT ON notes BEGIN "
        "INSERT INTO notes_fts(rowid, title, content) VALUES (new.rowid, new.title, new.content); END"
    )
    conn.commit()
    conn.execute(
        "INSERT INTO notes (id, title, content) VALUES ('n1', 'Test', 'some content')"
    )
    conn.commit()

    result = _fetch_related_notes(conn, "xyznonexistent")
    assert result == ""
    print("PASS test_fetch_related_notes_no_match")


def test_assemble_context_injects_related_notes():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE notes (id TEXT, title TEXT, content TEXT, status TEXT DEFAULT 'live', "
        "deleted_at TEXT, tags_json TEXT DEFAULT '[]', created_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        'CREATE VIRTUAL TABLE notes_fts USING fts5(title, content, content="notes", content_rowid="rowid")'
    )
    conn.execute(
        "CREATE TRIGGER notes_fts_insert AFTER INSERT ON notes BEGIN "
        "INSERT INTO notes_fts(rowid, title, content) VALUES (new.rowid, new.title, new.content); END"
    )
    conn.execute(
        "CREATE TABLE messages (id TEXT, session_id TEXT, agent_id TEXT DEFAULT 'knowledge', "
        "role TEXT, content TEXT, created_at TEXT)"
    )
    conn.commit()

    conn.execute(
        "INSERT INTO notes (id, title, content) VALUES ('n1', 'Knowledge Graph', 'thinking about graphs')"
    )
    conn.execute(
        "INSERT INTO messages (id, session_id, role, content) VALUES (?, 's1', 'user', 'hello')",
        (str(uuid.uuid4()),),
    )
    conn.execute(
        "INSERT INTO messages (id, session_id, role, content) VALUES (?, 's1', 'assistant', 'hi')",
        (str(uuid.uuid4()),),
    )
    conn.commit()

    # With user_input — should inject related notes
    msgs = assemble_context(conn, "s1", user_input="knowledge graph")
    contents = [m.content for m in msgs]
    assert any("相关" in c for c in contents), f"Missing related notes: {contents}"
    print("PASS test_assemble_context_injects_related_notes")


def test_assemble_context_no_user_input():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE messages (id TEXT, session_id TEXT, agent_id TEXT DEFAULT 'knowledge', "
        "role TEXT, content TEXT, created_at TEXT)"
    )
    conn.commit()

    conn.execute(
        "INSERT INTO messages (id, session_id, role, content) VALUES (?, 's1', 'user', 'hello')",
        (str(uuid.uuid4()),),
    )
    conn.commit()

    msgs = assemble_context(conn, "s1")
    contents = [m.content for m in msgs]
    assert not any("相关" in c for c in contents), f"Should not inject notes: {contents}"
    print("PASS test_assemble_context_no_user_input")


if __name__ == "__main__":
    tests = [
        test_fetch_related_notes_finds_match,
        test_fetch_related_notes_no_match,
        test_assemble_context_injects_related_notes,
        test_assemble_context_no_user_input,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
