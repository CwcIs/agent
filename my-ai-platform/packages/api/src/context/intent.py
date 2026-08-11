"""Explicit task intent carried across Router Graph nodes and checkpoints."""

from __future__ import annotations

from typing import Literal

from typing_extensions import TypedDict


class ReferencedFile(TypedDict, total=False):
    name: str
    path: str
    status: Literal["available", "missing", "pending", "processed"]


class IntentState(TypedDict):
    current_goal: str
    task_status: Literal["active", "waiting", "completed", "blocked"]
    referenced_files: list[ReferencedFile]


def build_intent_state(
    user_input: str,
    *,
    current_goal: str = "",
    task_status: str = "active",
    referenced_files: list[dict] | None = None,
) -> IntentState:
    allowed_statuses = {"active", "waiting", "completed", "blocked"}
    normalized_files: list[ReferencedFile] = []
    for item in referenced_files or []:
        name = str(item.get("name", "")).strip()
        path = str(item.get("path", "")).strip()
        status = str(item.get("status", "available"))
        if not name and not path:
            continue
        if status not in {"available", "missing", "pending", "processed"}:
            status = "available"
        normalized_files.append(
            {"name": name or path.rsplit("/", 1)[-1], "path": path, "status": status}
        )
    return {
        "current_goal": current_goal.strip() or user_input.strip(),
        "task_status": task_status if task_status in allowed_statuses else "active",
        "referenced_files": normalized_files,
    }


def format_intent_context(intent: IntentState) -> str:
    files = intent["referenced_files"]
    file_lines = "\n".join(
        f'- {item["name"]} [{item["status"]}] {item.get("path", "")}'.rstrip()
        for item in files
    ) or "- 无"
    return (
        "## 当前任务状态\n"
        f'目标：{intent["current_goal"]}\n'
        f'状态：{intent["task_status"]}\n'
        f"引用文件：\n{file_lines}"
    )
