"""Todo service · 从 asset 状态实时推导工作台「本周待办」列表.

设计:
    - 无独立存储; 每次调用扫一遍当前项目的 _assets, 按规则映射.
    - 单 asset 最多 1 条 todo (优先级: revision > review > redaction >
      publish > generate; 越紧急越优先).
    - asset.id 隐含跳转 URL: /projects/<pid>/documents/<aid>.

T128 新增 pending_revision 规则:
    asset.approval_state='rejected'  AND  status ∈ {draft, in_review}
    → 触发. 提示作者去 DocumentPage 看 reviewer 退回的章节理由.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.schemas.todo import TodoItem, TodoType

if TYPE_CHECKING:
    from app.schemas.asset import Asset


# 卡住超时 (秒): generating 状态超过此值 → pending_generate todo
_GENERATING_STUCK_SECONDS = 300


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _todo_type_for_asset(asset: "Asset") -> TodoType | None:
    """决定单个 asset 产生哪种 todo (None = 无 todo).

    优先级 (高 → 低):
      1. pending_revision  · 章节被退回, 作者侧最紧急
      2. pending_review    · 等 reviewer 处理
      3. pending_publish   · 已通过等发布
      4. pending_redaction · 草稿待脱敏
      5. pending_generate  · 卡住的 generating
    """
    # T128: rejected 优先级最高 (作者必须先修)
    if asset.approval_state == "rejected" and asset.status in ("draft", "in_review"):
        return "pending_revision"
    if asset.status == "in_review":
        return "pending_review"
    if asset.status == "approved":
        return "pending_publish"
    if asset.status == "draft" and asset.redaction_state == "any_unresolved":
        return "pending_redaction"
    if asset.status == "generating":
        # 用 updated_at 判断"卡住" (没 started_at 字段, 退而求其次)
        try:
            updated = datetime.fromisoformat(
                str(asset.updated_at).replace("Z", "+00:00")
            )
            elapsed = (datetime.now(timezone.utc) - updated).total_seconds()
            if elapsed > _GENERATING_STUCK_SECONDS:
                return "pending_generate"
        except (ValueError, TypeError):
            # updated_at 格式异常 → 不阻塞主流程
            return None
    return None


def _title_for_todo(asset: "Asset", todo_type: TodoType) -> str:
    """根据 asset.type + todo 类型给一个友好标题."""
    type_label = {
        "weekly_report": "周报",
        "tech_design": "技术方案",
        "adr": "ADR",
        "incident": "故障复盘",
        "book": "技术手册",
        "agent_skill": "Agent 技能",
        "knowledge_graph": "知识图谱",
    }.get(asset.type, asset.type)
    asset_title = asset.title or f"{type_label} (无标题)"
    prefix = {
        "pending_revision": "修订",
        "pending_review": "审批",
        "pending_publish": "发布",
        "pending_redaction": "脱敏",
        "pending_generate": "卡住",
    }[todo_type]
    return f"{prefix}: {asset_title}"


def list_todos(project_id: str) -> list[TodoItem]:
    """列项目下当前所有 todo (推导式, 无存储).

    Returns: TodoItem 列表, 已按 priority + updated_at desc 排好序.
    """
    # 延迟 import 避开循环 (todo_service ← generation_service ← gateway)
    from app.services import generation_service

    todos: list[TodoItem] = []
    now_iso = _iso_now()
    for asset in generation_service._assets.values():
        if asset.project_id != project_id:
            continue
        todo_type = _todo_type_for_asset(asset)
        if todo_type is None:
            continue
        todos.append(
            TodoItem(
                id=f"todo-{asset.id}",
                type=todo_type,
                title=_title_for_todo(asset, todo_type),
                asset_id=asset.id,
                due_at=None,
                created_at=str(asset.updated_at) or now_iso,
            )
        )
    # 双 stable sort: 先按 created_at desc, 再按 priority asc.
    # Python sort 稳定 → 同 priority 内保持上一步的 created_at desc 序.
    priority = {
        "pending_revision": 1,
        "pending_review": 2,
        "pending_publish": 3,
        "pending_redaction": 4,
        "pending_generate": 5,
    }
    todos.sort(key=lambda t: t.created_at, reverse=True)
    todos.sort(key=lambda t: priority.get(t.type, 99))
    return todos
