"""v1.3.1 T96 · entity_registry — project 级实体规范化 & 跨 KG asset 关联.

设计:
  - 入口 1: register_entity(project_id, node, asset_id, chapter_id) — assess stage 调用
  - 入口 2: list_entities(project_id, ...) — API 列表
  - 入口 3: get_sources(entity_id, asset_lookup_fn) — 反查 source assets
  - 入口 4: get_entity_for_node(project_id, node_id) — 节点 → entity
  - 内存 store (MVP), 与 generation_service _assets 风格一致; v1.4+ 上 sqlite

正交于 _stage_assess_knowledge_graph 的去重: 那里是 asset 内去重; 这里是
project 跨 asset 去重 (不破坏 asset 内 node id, 只建立 entity_id 映射).
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Iterable
from uuid import uuid4

import structlog

from app.schemas.entity_registry import (
    EntitySourceItem,
    EntitySourceRef,
    KGNodeType,
    ProjectEntity,
)

logger = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical(label: str) -> str:
    """规范化 label: trim + lower + collapse whitespace."""
    return " ".join((label or "").strip().lower().split())


# ── 内存 store ─────────────────────────────────────────────────────


_entities: dict[str, ProjectEntity] = {}
"""entity_id → ProjectEntity"""

_by_canonical: dict[tuple[str, KGNodeType, str], str] = {}
"""(project_id, type, canonical_label) → entity_id"""

_node_to_entity: dict[tuple[str, str], str] = {}
"""(asset_id, node_id) → entity_id (用于前端反查)"""

_lock = RLock()


def clear_for_test() -> None:
    """仅测试用: 重置全部内存 state."""
    with _lock:
        _entities.clear()
        _by_canonical.clear()
        _node_to_entity.clear()


# ── 核心入口 ──────────────────────────────────────────────────────


def register_entity(
    *,
    project_id: str,
    node_id: str,
    node_type: KGNodeType,
    label: str,
    asset_id: str,
    chapter_id: str,
) -> str:
    """注册节点到 project entity registry. 同名同 type 节点会被 merge 到同一 entity.

    返回 entity_id.
    """
    canon = _canonical(label)
    if not canon:
        # 空 label 不规范化; 给独立 entity_id (退化为 node 级 entity)
        canon = f"__anon__{node_id}"

    key = (project_id, node_type, canon)
    with _lock:
        eid = _by_canonical.get(key)
        ref = EntitySourceRef(
            asset_id=asset_id, chapter_id=chapter_id, node_id=node_id,
        )
        now = _now()
        if eid is None:
            eid = f"ent_{uuid4().hex[:12]}"
            _entities[eid] = ProjectEntity(
                id=eid, project_id=project_id, type=node_type,
                canonical_label=canon, label=label,
                aliases=[], source_refs=[ref],
                first_seen_at=now, last_seen_at=now,
            )
            _by_canonical[key] = eid
        else:
            ent = _entities[eid]
            # alias: label 与已知 label/aliases 不同时收入
            if label != ent.label and label not in ent.aliases:
                ent.aliases.append(label)
            # ref: 同 (asset_id, chapter_id, node_id) 不重复
            if not any(
                r.asset_id == ref.asset_id
                and r.chapter_id == ref.chapter_id
                and r.node_id == ref.node_id
                for r in ent.source_refs
            ):
                ent.source_refs.append(ref)
            ent.last_seen_at = now

        _node_to_entity[(asset_id, node_id)] = eid
        return eid


def register_asset_nodes(
    *,
    project_id: str,
    asset_id: str,
    chapter_id: str,
    nodes: Iterable[dict],
) -> dict[str, str]:
    """批量: assess stage 写完 layout 后调一次.

    返回 {node_id: entity_id} 映射.
    """
    out: dict[str, str] = {}
    for n in nodes:
        node_type = n.get("type")
        node_id = n.get("id")
        label = n.get("label", "")
        if node_type not in ("person", "event", "concept", "artifact"):
            continue
        if not node_id:
            continue
        eid = register_entity(
            project_id=project_id,
            node_id=node_id,
            node_type=node_type,  # type: ignore[arg-type]
            label=label,
            asset_id=asset_id,
            chapter_id=chapter_id,
        )
        out[node_id] = eid
    logger.info(
        "entity_registry_assoc",
        project_id=project_id,
        asset_id=asset_id,
        nodes=len(out),
    )
    return out


# ── 查询 ──────────────────────────────────────────────────────────


def list_entities(
    project_id: str,
    *,
    entity_type: KGNodeType | None = None,
    query: str | None = None,
    min_asset_count: int = 1,
) -> list[ProjectEntity]:
    """列 project 实体. query 走 canonical_label substring + label/aliases substring."""
    q = _canonical(query) if query else None
    out: list[ProjectEntity] = []
    with _lock:
        for ent in _entities.values():
            if ent.project_id != project_id:
                continue
            if entity_type and ent.type != entity_type:
                continue
            if ent.asset_count < min_asset_count:
                continue
            if q:
                hay = " ".join(
                    [ent.canonical_label, ent.label.lower(), *(a.lower() for a in ent.aliases)]
                )
                if q not in hay:
                    continue
            out.append(ent)
    # 按 asset_count desc, 然后 label 排
    out.sort(key=lambda e: (-e.asset_count, e.canonical_label))
    return out


def get_entity(entity_id: str) -> ProjectEntity | None:
    with _lock:
        return _entities.get(entity_id)


def get_entity_for_node(asset_id: str, node_id: str) -> ProjectEntity | None:
    with _lock:
        eid = _node_to_entity.get((asset_id, node_id))
        return _entities.get(eid) if eid else None


def get_sources(
    entity_id: str,
    *,
    asset_lookup: Callable[[str], dict | None],
) -> list[EntitySourceItem]:
    """asset 维度合并 source_refs.

    `asset_lookup` 接收 asset_id 返回 dict-like {title, type}; None 表示 asset 已删.
    """
    with _lock:
        ent = _entities.get(entity_id)
    if not ent:
        return []
    by_asset: dict[str, EntitySourceItem] = {}
    for r in ent.source_refs:
        if r.asset_id not in by_asset:
            asset = asset_lookup(r.asset_id)
            if asset is None:
                continue  # asset 已删
            by_asset[r.asset_id] = EntitySourceItem(
                asset_id=r.asset_id,
                asset_title=asset.get("title", "(untitled)"),
                asset_type=asset.get("type", "knowledge_graph"),
                chapter_ids=[],
                node_ids=[],
            )
        item = by_asset[r.asset_id]
        if r.chapter_id not in item.chapter_ids:
            item.chapter_ids.append(r.chapter_id)
        if r.node_id not in item.node_ids:
            item.node_ids.append(r.node_id)
    return list(by_asset.values())
