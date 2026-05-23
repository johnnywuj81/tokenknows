"""v1.6 T102 · entity merge/split audit log + undo.

设计:
  - merge/split endpoint 调用前先 record_* 记快照 → 后才执行 merge/split
  - undo_split: 重建 merged entity 状态; merge undo 留 v1.7 (复杂度高)
  - MVP 内存 store; v1.7 升级 sqlite

注: merge undo 难度高 (需检查 target 期间是否被改); v1.6 只支持 split undo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

import structlog

from app.schemas.entity_registry import (
    EntityAuditLog,
    EntitySourceRef,
    ProjectEntity,
)
from app.services.knowledge_graph import entity_registry as registry

logger = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── 内存 store ─────────────────────────────────────────────────────


_logs: dict[str, EntityAuditLog] = {}
"""audit_log_id → EntityAuditLog"""

_lock = RLock()


def clear_for_test() -> None:
    with _lock:
        _logs.clear()


# ── record ────────────────────────────────────────────────────────


def record_merge(
    *,
    project_id: str,
    source: ProjectEntity,
    target_id: str,
    target_label: str,
    actor_id: str | None = None,
) -> EntityAuditLog:
    """merge 执行 *前* 调; 记录 source 的完整快照供 (v1.7) undo."""
    with _lock:
        log_id = f"audit_{uuid4().hex[:12]}"
        log = EntityAuditLog(
            id=log_id, project_id=project_id, op_type="merge",
            actor_id=actor_id, created_at=_now(),
            payload={
                "source_snapshot": source.model_dump(mode="json"),
                "target_id": target_id,
                "target_label": target_label,
            },
        )
        _logs[log_id] = log
        logger.info(
            "entity_audit_merge",
            log_id=log_id, project_id=project_id,
            source_id=source.id, target_id=target_id, actor=actor_id,
        )
        return log


def record_split(
    *,
    project_id: str,
    source_id: str,
    new_entity_id: str,
    moved_node_ref: EntitySourceRef,
    new_canonical: str,
    actor_id: str | None = None,
) -> EntityAuditLog:
    """split 执行 *后* 调; 记录拆出的 new_entity_id 用于 undo."""
    with _lock:
        log_id = f"audit_{uuid4().hex[:12]}"
        log = EntityAuditLog(
            id=log_id, project_id=project_id, op_type="split",
            actor_id=actor_id, created_at=_now(),
            payload={
                "source_id": source_id,
                "new_entity_id": new_entity_id,
                "moved_node_ref": moved_node_ref.model_dump(mode="json"),
                "new_canonical": new_canonical,
            },
        )
        _logs[log_id] = log
        logger.info(
            "entity_audit_split",
            log_id=log_id, project_id=project_id,
            source_id=source_id, new_entity_id=new_entity_id, actor=actor_id,
        )
        return log


# ── list / get ────────────────────────────────────────────────────


def list_logs(
    project_id: str,
    *,
    op_type: str | None = None,
    only_undoable: bool = False,
    limit: int = 100,
) -> list[EntityAuditLog]:
    with _lock:
        out: list[EntityAuditLog] = []
        for log in _logs.values():
            if log.project_id != project_id:
                continue
            if op_type and log.op_type != op_type:
                continue
            if only_undoable and (log.undone or log.op_type == "merge"):
                continue
            out.append(log)
    # newest first
    out.sort(key=lambda l: l.created_at, reverse=True)
    return out[:limit]


def get_log(log_id: str) -> EntityAuditLog | None:
    with _lock:
        return _logs.get(log_id)


# ── undo ──────────────────────────────────────────────────────────


def undo_split(log_id: str, *, actor_id: str | None = None) -> EntityAuditLog | None:
    """v1.6 T102 · 撤销一次 split 操作.

    动作:
        - 检查 new_entity 仍存在且只有 1 个 source_ref (没被后续改动); 否则拒绝
        - 把 new_entity 的唯一 ref 移回 source entity
        - 删 new_entity (含 _by_canonical + _node_to_entity 清理)
        - log.undone = True

    失败原因:
        - log 不存在
        - op_type ≠ 'split'
        - 已 undone
        - source 已不存在 (e.g. 后续被合并删了)
        - new_entity 已不存在或被改动
    """
    with _lock:
        log = _logs.get(log_id)
        if log is None or log.op_type != "split" or log.undone:
            return None
        payload = log.payload
        source_id = payload["source_id"]
        new_ent_id = payload["new_entity_id"]
        moved_ref_data = payload["moved_node_ref"]
        moved_ref = EntitySourceRef(**moved_ref_data)

        # 同步访问 project_registry 内部 state
        # 检查 source 和 new_entity 当前状态
        src = registry.get_entity(source_id)
        new_ent = registry.get_entity(new_ent_id)
        if src is None or new_ent is None:
            return None
        # 防御: new_entity 应当仍是 split 时的状态 (单 ref, 同 type)
        if len(new_ent.source_refs) != 1:
            return None
        if new_ent.type != src.type:
            return None

        # 把 ref 移回 src
        # 防御: ref 应当与 payload 中的 moved_node_ref 一致
        actual = new_ent.source_refs[0]
        if (
            actual.asset_id != moved_ref.asset_id
            or actual.chapter_id != moved_ref.chapter_id
            or actual.node_id != moved_ref.node_id
        ):
            return None

        # 检查 src 没已经有相同 ref (理论不可能, 防御)
        if any(
            r.asset_id == moved_ref.asset_id
            and r.chapter_id == moved_ref.chapter_id
            and r.node_id == moved_ref.node_id
            for r in src.source_refs
        ):
            # ref 已经在 src 中, 仅删 new_entity
            pass
        else:
            src.source_refs.append(moved_ref)
        src.last_seen_at = _now()

        # reroute node_to_entity
        registry._node_to_entity[(moved_ref.asset_id, moved_ref.node_id)] = source_id

        # 删 new_entity
        registry._by_canonical.pop(
            (new_ent.project_id, new_ent.type, new_ent.canonical_label),
            None,
        )
        registry._entities.pop(new_ent_id, None)

        log.undone = True
        log.undone_at = _now()
        log.undone_by = actor_id
        logger.info(
            "entity_audit_undo_split",
            log_id=log_id, source_id=source_id,
            new_entity_id=new_ent_id, actor=actor_id,
        )
        return log
