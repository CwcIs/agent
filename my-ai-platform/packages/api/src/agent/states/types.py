# ============================================================
# 全局类型定义
# 对应 MD：
#   §2 场景 C — NoteStatus / NoteCitation / CollisionReport
#   §2 场景 D — DailyDigest
#   §4.1 AgentAdapter 接口 — AgentChunk（text / tool_use / tool_result 三件套）
#   §4.3 笔记数据模型 — Note（6 表核心字段）
#   §4.6 会话上下文 — RequestContext
#   §8.5 — LLMCallRecord（llm_calls 表对应）
#
# 用 Pydantic BaseModel 定义，既是类型标注也是运行时校验
# ============================================================

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---- 笔记状态（§2 场景 C） ----
# live = 当前有效，可被 AI 引用
# superseded = 被另一条笔记取代，superseded_by 指向新笔记 id
# archived = 用户手动归档，不参与召回
class NoteStatus(str, Enum):
    LIVE = "live"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


# ---- 笔记（§4.3 notes 表） ----
# 对应 SQL：notes(id, title, content, summary, tags_json, ...)
class Note(BaseModel):
    id: str
    title: str
    content: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    source: str = ""
    status: NoteStatus = NoteStatus.LIVE
    superseded_by: Optional[str] = None        # 被哪条新笔记取代
    confidence: Optional[float] = None         # AI 提炼置信度 0-1
    schema_version: int = 1                    # 数据迁移用
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    deleted_at: Optional[datetime] = None      # 软删除，不真删


# ---- 引用（§2 场景 C） ----
# AI 输出引用时每条必须挂 noteId + 日期，可点回原笔记核对
class NoteCitation(BaseModel):
    note_id: str
    title: str
    date: str                                  # 原始创建日期
    confidence: float = Field(ge=0.0, le=1.0)  # AI 自评引用可靠度
    conflict_with: Optional[str] = None        # 如果引用到已 superseded 的笔记


class CollisionReport(BaseModel):
    """想法碰撞报告 — 支持点 + 反对点 + 冲突标记 + 下一步追问"""
    support: dict[str, Any]     # { text, citations: list[NoteCitation] }
    critique: dict[str, Any]    # 同上
    conflicts: list[NoteCitation] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)  # 恰好 3 个追问


# ---- 每日摘要（§2 场景 D） ----
class DailyDigest(BaseModel):
    date: str                                  # YYYY-MM-DD
    note_count: int = 0
    narrative: str = ""                        # 连贯综述（不是 bullet 堆叠）
    follow_ups: list[str] = Field(default_factory=list)  # 恰好 3 条
    cited_notes: list[NoteCitation] = Field(default_factory=list)


# ---- AgentChunk（§4.1） ----
# Adapter 必须吐带类型的 chunk 流，把 text / tool_use / tool_result 分开
class AgentChunk(BaseModel):
    type: Literal["text", "tool_use", "tool_result"]
    delta: str = ""                            # text 类型的增量
    tool_use_id: str = ""
    tool_name: str = ""
    tool_input: Any = None
    content: str = ""                          # tool_result 的内容
    is_error: bool = False


# ---- RequestContext（§4.6） ----
# 从 WS/HTTP 入口一路传到 Adapter 调用、Memory 读写、日志埋点
# sessionId 是 trace key，Phase 2 加 OpenTelemetry 时直接当 trace_id 用
class RequestContext(BaseModel):
    session_id: str
    prompt_version: str = "v1"                 # 从第一天就传，改 prompt 能回溯
    user_id: Optional[str] = None
    platform: Literal["web", "telegram"] = "web"


# ---- LLM 调用记录（§8.5 llm_calls 表） ----
class LLMCallRecord(BaseModel):
    id: str
    session_id: str
    prompt_version: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float = 0.0
    latency_ms: int = 0
    status: Literal["ok", "error", "retry"] = "ok"
    created_at: datetime = Field(default_factory=datetime.now)
