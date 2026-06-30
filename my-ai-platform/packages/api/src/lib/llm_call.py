# ============================================================
# 统一 call_llm() 封装
# 对应 MD §5.5 工程基础六项之"llm-call 重试"
#
# 职责：
#   1. 统一入口 — 所有 LLM 调用走这里（Claude / GPT / Gemini）
#   2. 指数退避重试 — 429 等 retry-after，5xx 退避重试，
#      网络错误重试 3 次，4xx（除 429）直接抛
#   3. Token 预算校验 — 调 assert_within_budget() 先判
#   4. 可观测性日志 — trace_id / session_id / prompt_version 贯穿
#   5. 计费埋点 — 写入 llm_calls 表
#
# 为什么必须有统一封装（MD §5.5）：
#   三家 API 各自的重试逻辑写三遍会失控，行为不一致
#
# 骨架（MD §5.5 伪代码）：
#   for attempt in range(3):
#       try:
#           resp = providers[provider](messages)
#           logger.info({trace_id, provider, tokens, ...})
#           record_tokens(session_id, resp.usage)
#           return resp
#       except (429): sleep(retry_after || 2**attempt)
#       except (5xx, NetworkError): sleep(500 * 2**attempt)
#       else: raise  # 4xx 直接抛
#   raise RuntimeError("call_llm failed after 3 attempts")
# ============================================================

import asyncio
import logging
import sqlite3
import time
import uuid
from typing import Any

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage

from src.lib.budget import BudgetExceededError, assert_within_budget

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


# 各模型每 1k token 的美元成本（input, output）
# Phase 1 只用 Claude，其他占位
_COST_PER_1K: dict[str, tuple[float, float]] = {
    "claude-3-5-haiku-20241022":  (0.0008, 0.004),
    "claude-3-5-sonnet-20241022": (0.003,  0.015),
    "deepseek-chat":              (0.00027, 0.0011),
}


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = _COST_PER_1K.get(model, (0.001, 0.005))
    return (input_tokens * in_rate + output_tokens * out_rate) / 1000


def _record_call(
    conn: sqlite3.Connection,
    session_id: str,
    prompt_version: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    status: str,
    trace_id: str = "",
    agent_id: str = "",
) -> None:
    cost = _calc_cost(model, input_tokens, output_tokens)
    conn.execute(
        """INSERT INTO llm_calls
           (id, session_id, prompt_version, model,
            input_tokens, output_tokens, cost_usd, latency_ms, status, trace_id, agent_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (str(uuid.uuid4()), session_id, prompt_version, model,
         input_tokens, output_tokens, cost, latency_ms, status, trace_id, agent_id),
    )
    conn.commit()


async def call_llm(
    llm: BaseChatModel,
    messages: list[BaseMessage],
    conn: sqlite3.Connection,
    session_id: str,
    prompt_version: str = "v1",
    trace_id: str = "",
    agent_id: str = "",
) -> Any:
    """
    统一 LLM 调用入口。

    - 调用前先 assert_within_budget()
    - 429 / 5xx / 网络错误最多重试 3 次，指数退避
    - 4xx（非 429）直接抛，不重试
    - 成功或失败都写 llm_calls 表
    """
    # 预算检查——超额直接抛，不消耗重试次数
    assert_within_budget(conn, session_id)

    model_name: str = getattr(llm, "model_name", getattr(llm, "model", "unknown"))
    last_exc: Exception | None = None

    for attempt in range(MAX_ATTEMPTS):
        t0 = time.monotonic()
        status = "ok"
        try:
            response = await llm.ainvoke(messages)
            latency_ms = int((time.monotonic() - t0) * 1000)

            usage = getattr(response, "usage_metadata", None) or {}
            input_tokens = usage.get("input_tokens", 0) if isinstance(usage, dict) else getattr(usage, "input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0) if isinstance(usage, dict) else getattr(usage, "output_tokens", 0)

            _record_call(conn, session_id, prompt_version, model_name,
                         input_tokens, output_tokens, latency_ms, "ok", trace_id, agent_id)

            logger.info(
                "llm_call ok session=%s model=%s in=%d out=%d latency=%dms attempt=%d",
                session_id, model_name, input_tokens, output_tokens, latency_ms, attempt + 1,
            )
            return response

        except BudgetExceededError:
            raise  # 预算超额不重试

        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            last_exc = exc
            exc_str = str(exc)

            # 判断是否 429 或 5xx
            is_429 = "429" in exc_str or "rate_limit" in exc_str.lower()
            is_5xx = any(c in exc_str for c in ("500", "502", "503", "504"))
            is_network = isinstance(exc, (httpx.NetworkError, httpx.TimeoutException, ConnectionError))

            if not (is_429 or is_5xx or is_network):
                # 4xx 非 429：记录后直接抛，不重试
                status = "error"
                _record_call(conn, session_id, prompt_version, model_name,
                             0, 0, latency_ms, status, trace_id, agent_id)
                logger.error("llm_call 4xx session=%s err=%s", session_id, exc_str)
                raise

            # 可重试错误：记录 retry 状态，等待后继续
            if attempt < MAX_ATTEMPTS - 1:
                status = "retry"
                _record_call(conn, session_id, prompt_version, model_name,
                             0, 0, latency_ms, status, trace_id, agent_id)
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    "llm_call retry session=%s attempt=%d wait=%ds err=%s",
                    session_id, attempt + 1, wait, exc_str,
                )
                await asyncio.sleep(wait)
            else:
                status = "error"
                _record_call(conn, session_id, prompt_version, model_name,
                             0, 0, latency_ms, status, trace_id, agent_id)

    raise RuntimeError(f"call_llm failed after {MAX_ATTEMPTS} attempts") from last_exc
