# ============================================================
# Token 预算守卫（BudgetGuard）
# 对应 MD §5.5 工程基础六项之"token 预算"
#
# 职责：
#   - per-session 上限 + per-day 上限
#   - 超额返回 429（HTTP 层）或抛异常（内部调用）
#   - 累计查询 llm_calls 表当日 SUM(cost_usd)
#
# 为什么必须做（MD §5.5）：
#   一次 A2A 死循环烧光当月预算。
#   工程的顺序是固定的（MD §10 原则 9）：
#     成本上限 → prompt 版本化 → 统一重试/超时
#     → 可观测性 → secrets → 然后才轮到多模型/A2A
# ============================================================

import sqlite3


# 每日全局上限（美元）。超出后所有请求拒绝，直到次日重置。
DAY_LIMIT_USD = 2.0
# 单 session 单日上限
SESSION_LIMIT_USD = 0.50


class BudgetExceededError(Exception):
    """超出预算时抛出，调用方捕获后返回 HTTP 429"""
    def __init__(self, msg: str):
        super().__init__(msg)
        self.msg = msg


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def get_day_cost(conn: sqlite3.Connection) -> float:
    """查询今日所有 session 累计花费（美元）"""
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE created_at >= ?",
        (_today(),),
    ).fetchone()
    return float(row[0])


def get_session_cost(conn: sqlite3.Connection, session_id: str) -> float:
    """查询指定 session 今日累计花费（美元）"""
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls "
        "WHERE session_id = ? AND created_at >= ?",
        (session_id, _today()),
    ).fetchone()
    return float(row[0])


def assert_within_budget(conn: sqlite3.Connection, session_id: str) -> None:
    """
    调用 LLM 前先执行此检查。超额直接抛 BudgetExceededError。
    llm_call.py 在每次调用前调这个，不需要调用方记住。
    """
    day_cost = get_day_cost(conn)
    if day_cost >= DAY_LIMIT_USD:
        raise BudgetExceededError(
            f"今日全局花费 ${day_cost:.4f} 已达上限 ${DAY_LIMIT_USD}，请明日再试"
        )

    session_cost = get_session_cost(conn, session_id)
    if session_cost >= SESSION_LIMIT_USD:
        raise BudgetExceededError(
            f"session {session_id} 今日花费 ${session_cost:.4f} 已达上限 ${SESSION_LIMIT_USD}"
        )
