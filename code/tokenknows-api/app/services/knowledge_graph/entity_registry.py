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


def merge_entities(source_id: str, target_id: str) -> ProjectEntity | None:
    """v1.3.1 T98 · 把 source entity 合并到 target.

    校验:
        - source 与 target 必须同 project + 同 type (跨类型合并禁止)
        - source 不等于 target (no-op 也 reject)

    动作:
        - target.source_refs ∪= source.source_refs (按 (asset,chapter,node) 去重)
        - target.aliases ∪= [source.label] + source.aliases (按 string 去重)
        - target.last_seen_at = max
        - _node_to_entity 中所有指向 source 的 reroute 到 target
        - _by_canonical 中 source 的键删除 (canonical 不变, 因为 source 被吞)
        - _entities 中删 source
    返回合并后的 target; source/target 找不到 → None.
    """
    with _lock:
        if source_id == target_id:
            return None
        src = _entities.get(source_id)
        tgt = _entities.get(target_id)
        if src is None or tgt is None:
            return None
        if src.project_id != tgt.project_id:
            return None
        if src.type != tgt.type:
            return None

        # aliases ∪
        candidates = [src.label, *src.aliases]
        for label in candidates:
            if label != tgt.label and label not in tgt.aliases:
                tgt.aliases.append(label)

        # source_refs ∪
        existing_keys = {
            (r.asset_id, r.chapter_id, r.node_id) for r in tgt.source_refs
        }
        for r in src.source_refs:
            key = (r.asset_id, r.chapter_id, r.node_id)
            if key not in existing_keys:
                tgt.source_refs.append(r)
                existing_keys.add(key)

        tgt.last_seen_at = max(tgt.last_seen_at, src.last_seen_at)

        # reroute node mapping
        for k, v in list(_node_to_entity.items()):
            if v == source_id:
                _node_to_entity[k] = target_id

        # remove from canonical lookup (source key 可能与 target 不同)
        src_key = (src.project_id, src.type, src.canonical_label)
        if _by_canonical.get(src_key) == source_id:
            # source 的 canonical 与 target 不同时, 删除 source key;
            # 同 canonical 时, target 已占该 key (源已 merge), 直接删
            del _by_canonical[src_key]

        del _entities[source_id]
        return tgt


def split_node_to_new_entity(
    entity_id: str,
    *,
    asset_id: str,
    node_id: str,
    new_label: str | None = None,
    new_canonical_suffix: str | None = None,
) -> tuple[ProjectEntity, ProjectEntity] | None:
    """v1.3.1 T98 · 从 entity 中拆出指定 node, 创建新 entity 承接.

    场景: assess 把两个不同人误合 (都叫 'Alice', 实际不同人), Reviewer 在 UI 上
    选其中一个节点 "拆出"; 拆出后新 entity 与原 entity 同 type 同 project, 但
    canonical_label 加后缀防冲突 (默认 ' (split-<n>)').

    参数:
        entity_id: 要拆分的来源
        asset_id, node_id: 唯一定位 source_ref (同 entity 内多个 ref 时拆一条)
        new_label: 新 entity 的展示 label; None 时复用原 label
        new_canonical_suffix: canonical 后缀; None 自动生成

    返回 (updated_source, new_entity); 找不到 ref 时 None.
    """
    with _lock:
        src = _entities.get(entity_id)
        if src is None:
            return None
        # 找指定 ref
        target_ref = next(
            (r for r in src.source_refs
             if r.asset_id == asset_id and r.node_id == node_id),
            None,
        )
        if target_ref is None:
            return None
        if len(src.source_refs) <= 1:
            # 仅 1 个 ref, 拆了相当于 rename, 拒绝
            return None

        # 移除 ref
        src.source_refs = [r for r in src.source_refs if r is not target_ref]

        # 生成新 entity
        label = new_label or src.label
        suffix = new_canonical_suffix or f" (split-{uuid4().hex[:6]})"
        new_canonical = (src.canonical_label + suffix).strip().lower()
        new_id = f"ent_{uuid4().hex[:12]}"
        now = _now()
        new_ent = ProjectEntity(
            id=new_id,
            project_id=src.project_id,
            type=src.type,
            canonical_label=new_canonical,
            label=label,
            aliases=[],
            source_refs=[target_ref],
            first_seen_at=now,
            last_seen_at=now,
        )
        _entities[new_id] = new_ent
        _by_canonical[(src.project_id, src.type, new_canonical)] = new_id
        _node_to_entity[(target_ref.asset_id, target_ref.node_id)] = new_id
        return src, new_ent


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
