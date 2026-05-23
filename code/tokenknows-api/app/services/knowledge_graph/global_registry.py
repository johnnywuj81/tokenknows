"""v1.5 T99 · global_registry — 跨 project 全局实体.

设计:
  - 类比 Skill marketplace: project entity 显式 publish 到 global; 不自动同步
  - publish 时自动按 (type + canonical) 匹配已有 global; 命中则 link 现有, miss 则创建
  - 同 project_entity 可 publish 到不同 global (例如手动 re-link); 但同时只属于 1 个
    global. publish 替换语义.
  - global 不可跨 type 合并 (与 project registry 一致)
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

import structlog

from app.schemas.entity_registry import (
    GlobalEntity,
    GlobalEntityLink,
    KGNodeType,
    ProjectEntity,
)
from app.services.knowledge_graph import entity_registry as project_registry

logger = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── 内存 store ─────────────────────────────────────────────────────


_globals: dict[str, GlobalEntity] = {}
"""global_id → GlobalEntity"""

_by_canonical: dict[tuple[KGNodeType, str], str] = {}
"""(type, canonical_label) → global_id (单 global per canonical)"""

_project_to_global: dict[str, str] = {}
"""project_entity_id → global_id; 1:1 映射"""

_lock = RLock()


def clear_for_test() -> None:
    with _lock:
        _globals.clear()
        _by_canonical.clear()
        _project_to_global.clear()


# ── publish / link / unlink ──────────────────────────────────────


def publish_to_global(
    project_entity_id: str, *, actor_id: str | None = None,
) -> GlobalEntity | None:
    """v1.5 T99 · 把 project entity publish 到 global.

    行为:
        - project entity 已 linked 到 global → no-op, 返回当前 global
        - 同 (type, canonical) 已有 global → link 现有
        - 否则 → 创建新 global

    返回最终的 GlobalEntity; project entity 找不到 → None.
    """
    pent = project_registry.get_entity(project_entity_id)
    if pent is None:
        return None
    with _lock:
        existing = _project_to_global.get(project_entity_id)
        if existing:
            return _globals.get(existing)

        key = (pent.type, pent.canonical_label)
        gid = _by_canonical.get(key)
        link = GlobalEntityLink(
            project_id=pent.project_id, project_entity_id=project_entity_id,
        )
        now = _now()
        if gid is None:
            gid = f"gent_{uuid4().hex[:12]}"
            _globals[gid] = GlobalEntity(
                id=gid, type=pent.type,
                canonical_label=pent.canonical_label,
                label=pent.label,
                aliases=list(pent.aliases),
                linked=[link],
                created_by=actor_id,
                created_at=now, last_seen_at=now,
            )
            _by_canonical[key] = gid
        else:
            gent = _globals[gid]
            if not any(
                lk.project_id == link.project_id
                and lk.project_entity_id == link.project_entity_id
                for lk in gent.linked
            ):
                gent.linked.append(link)
            # 合并 aliases
            candidates = [pent.label, *pent.aliases]
            for label in candidates:
                if label != gent.label and label not in gent.aliases:
                    gent.aliases.append(label)
            gent.last_seen_at = now

        _project_to_global[project_entity_id] = gid
        logger.info(
            "global_entity_publish",
            project_entity_id=project_entity_id,
            global_id=gid,
            project_id=pent.project_id,
        )
        return _globals[gid]


def unlink_project_entity(project_entity_id: str) -> bool:
    """把 project entity 从 global 解除关联. global 自身保留 (可能还有其他 project link)."""
    with _lock:
        gid = _project_to_global.pop(project_entity_id, None)
        if gid is None:
            return False
        gent = _globals.get(gid)
        if gent:
            gent.linked = [
                lk for lk in gent.linked
                if lk.project_entity_id != project_entity_id
            ]
            # global 若空了, 删
            if not gent.linked:
                _globals.pop(gid, None)
                _by_canonical.pop((gent.type, gent.canonical_label), None)
        return True


# ── 查询 ──────────────────────────────────────────────────────────


def get_global(global_id: str) -> GlobalEntity | None:
    with _lock:
        return _globals.get(global_id)


def get_global_for_project_entity(
    project_entity_id: str,
) -> GlobalEntity | None:
    with _lock:
        gid = _project_to_global.get(project_entity_id)
        return _globals.get(gid) if gid else None


def list_globals(
    *,
    entity_type: KGNodeType | None = None,
    query: str | None = None,
    min_projects: int = 1,
) -> list[GlobalEntity]:
    q = (query or "").strip().lower()
    out: list[GlobalEntity] = []
    with _lock:
        for gent in _globals.values():
            if entity_type and gent.type != entity_type:
                continue
            if gent.project_count < min_projects:
                continue
            if q:
                hay = " ".join(
                    [gent.canonical_label, gent.label.lower(),
                     *(a.lower() for a in gent.aliases)]
                )
                if q not in hay:
                    continue
            out.append(gent)
    out.sort(key=lambda g: (-g.project_count, g.canonical_label))
    return out


def get_linked_project_entities(global_id: str) -> list[ProjectEntity]:
    """global → 关联的 project entities (从 project_registry 取详情)."""
    with _lock:
        gent = _globals.get(global_id)
        if gent is None:
            return []
        out: list[ProjectEntity] = []
        for lk in gent.linked:
            ent = project_registry.get_entity(lk.project_entity_id)
            if ent is not None:
                out.append(ent)
    return out
