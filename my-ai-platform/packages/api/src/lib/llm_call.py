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
