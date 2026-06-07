# ============================================================
# FastAPI SSE 端点
# 对应 MD §5.3 实时通信（SSE 替代 WebSocket）
#
# 路由：
#   GET  /chat/stream       — SSE 流式响应（LLM token + Agent 切换通知）
#   GET  /notes              — 笔记列表
#   POST /notes              — 保存笔记（备选 REST 入口）
#   GET  /digest             — 每日摘要
#   POST /abort              — 中断请求（Phase 2）
#
# 为什么 SSE 不是 WebSocket（MD §5.3）：
#   Phase 1 只有"服务端推客户端"是高频的，
#   "客户端推服务端"用普通 POST 完全够。
#   SSE 的好处：
#     - 浏览器原生 EventSource，不需要客户端库
#     - 没有握手开销
#     - 自动重连（Last-Event-ID）
#     - 跨代理友好（nginx/Cloudflare 直接过）
#
# FastAPI SSE 实现用 sse-starlette 库
# ============================================================
