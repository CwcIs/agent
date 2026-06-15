"""
WorklistRegistry 单元测试。

验证：
  1. save_handoff 创建 pending 记录
  2. mark_running / mark_done / mark_failed 状态转换
  3. get_pending 只返回未完成项
  4. cleanup_session 清理已完成/失败项
"""

import json
import os
import sqlite3
import tempfile

import pytest

from src.agent.worklist import (
    save_handoff,
    mark_running,
    mark_done,
    mark_failed,
    get_pending,
    get_by_id,
    cleanup_session,
)
from src.db.schema import init_db


@pytest.fixture
def conn():
    """创建带 worklist 表的临时数据库。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    init_db(db)
    yield db
    db.close()
    os.unlink(path)


class TestWorklistCRUD:
    """worklist 表 CRUD 操作测试。"""

    def test_save_and_get(self, conn):
        """save_handoff 后 get_by_id 能取回完整字段。"""
        wid = save_handoff(
            conn,
            session_id="s1",
            agent_id="review",
            depth=1,
            user_input="test input",
            agent_a_output="@review 挑战",
            mention_content="挑战",
            tool_events=[{"type": "tool_end", "name": "search", "result": "ok"}],
        )
        assert wid

        item = get_by_id(conn, wid)
        assert item is not None
        assert item["session_id"] == "s1"
        assert item["agent_id"] == "review"
        assert item["depth"] == 1
        assert item["status"] == "pending"
        assert item["user_input"] == "test input"
        assert item["agent_a_output"] == "@review 挑战"
        assert item["mention_content"] == "挑战"
        events = json.loads(item["tool_events_json"])
        assert len(events) == 1
        assert events[0]["name"] == "search"

    def test_status_lifecycle(self, conn):
        """pending → running → done 完整生命周期。"""
        wid = save_handoff(conn, "s1", "review", 0, "in", "out", "mention", [])

        item = get_by_id(conn, wid)
        assert item["status"] == "pending"

        mark_running(conn, wid)
        item = get_by_id(conn, wid)
        assert item["status"] == "running"

        mark_done(conn, wid)
        item = get_by_id(conn, wid)
        assert item["status"] == "done"

    def test_mark_failed(self, conn):
        """mark_failed 记录 error_msg。"""
        wid = save_handoff(conn, "s1", "review", 0, "in", "out", "mention", [])
        mark_failed(conn, wid, "timeout")
        item = get_by_id(conn, wid)
        assert item["status"] == "failed"
        assert item["error_msg"] == "timeout"

    def test_get_pending_only_incomplete(self, conn):
        """get_pending 只返回 pending 和 running，不返回 done/failed。"""
        w1 = save_handoff(conn, "s1", "review", 0, "in", "out", "m1", [])
        w2 = save_handoff(conn, "s1", "knowledge", 0, "in", "out", "m2", [])
        w3 = save_handoff(conn, "s1", "review", 0, "in", "out", "m3", [])

        mark_done(conn, w2)
        mark_failed(conn, w3)

        pending = get_pending(conn, "s1")
        assert len(pending) == 1
        assert pending[0]["id"] == w1

    def test_cleanup_removes_done_and_failed(self, conn):
        """cleanup_session 删除 done 和 failed，保留 pending。"""
        w1 = save_handoff(conn, "s1", "review", 0, "in", "out", "m1", [])
        w2 = save_handoff(conn, "s1", "knowledge", 0, "in", "out", "m2", [])

        mark_done(conn, w2)
        n = cleanup_session(conn, "s1")
        assert n == 1  # 只删了 w2 (done)

        pending = get_pending(conn, "s1")
        assert len(pending) == 1
        assert pending[0]["id"] == w1

        assert get_by_id(conn, w2) is None
