"""TodoItem · 工作台「本周待办」schema.

设计原则 (与 web/src/types/api.ts:TodoItem 镜像):
    - 不在 SQLite 单独建表; todos 是 asset 状态的 view (实时按规则推导).
    - 5 种类型, 同一 asset 最多产生 1 条 todo (优先级见 todo_service).

类型说明:
    pending_generate  → asset.status='generating' 但已过 N 分钟 (卡住)
    pending_redaction → asset.redaction_state='any_unresolved' 且 draft 后
    pending_review    → asset.status='in_review' (reviewer 视角)
    pending_revision  → asset.approval_state='rejected' (T128 新增 · 作者视角)
    pending_publish   → asset.status='approved' 等发布
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

TodoType = Literal[
    "pending_generate",
    "pending_redaction",
    "pending_review",
    "pending_revision",  # T128 · 章节被退回, 作者需修订
    "pending_publish",
]


class TodoItem(BaseModel):
    """前端 TodoList 的最小渲染单元."""

    id: str
    type: TodoType
    title: str
    asset_id: str | None = None
    """点击跳转用; null 时表示无 asset 关联 (目前所有类型都有 asset)."""
    due_at: str | None = None
    """ISO 8601 字符串; null 表示无截止 (UI 不会标 overdue)."""
    created_at: str
    """ISO 8601 字符串; 用于排序."""
