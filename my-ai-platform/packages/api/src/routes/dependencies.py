"""Shared route dependencies."""

import sqlite3

from fastapi import HTTPException

_conn: sqlite3.Connection | None = None


def set_connection(conn: sqlite3.Connection) -> None:
    global _conn
    _conn = conn


def get_conn() -> sqlite3.Connection:
    if _conn is None:
        raise HTTPException(500, "db not initialized")
    return _conn

