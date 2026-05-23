"""v1.3.1 T96 · GET /projects/:pid/entities + GET /entities/:eid + sources.

跨 KG asset 的 project 级实体规范化 (人/事件/概念/产物).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.gateway.http_api._session import get_current_user_id
from app.schemas.entity_registry import (
    EntityAuditLog,
    EntitySourceItem,
    GlobalEntity,
    ProjectEntity,
)
from app.services import generation_service as svc
from app.services.knowledge_graph import audit as audit_service
from app.services.knowledge_graph import entity_registry as registry
from app.services.knowledge_graph import global_registry

router = APIRouter()


# ── T98 · merge / split DTOs ──────────────────────────────────────


class MergeEntitiesRequest(BaseModel):
    """T98 · 把 source merge 到 target. 两实体必须同 project + 同 type."""

    target_id: str


class EntitiesMergedResult(BaseModel):
    """T98 · merge 后的 target snapshot (source 已删)."""

    target: ProjectEntity


class SplitNodeRequest(BaseModel):
    """T98 · 从 entity 中把指定 node ref 拆成新 entity."""

    asset_id: str
    node_id: str
    new_label: str | None = None


class EntitiesSplitResult(BaseModel):
    """T98 · split 后双方."""

    source: ProjectEntity
    new_entity: ProjectEntity


@router.get(
    "/projects/{project_id}/entities",
    response_model=list[ProjectEntity],
)
async def list_project_entities(
    project_id: str,
    type: Literal["person", "event", "concept", "artifact"] | None = Query(
        None, description="按类型过滤",
    ),
    q: str | None = Query(None, description="模糊匹配 label/aliases"),
    min_assets: int = Query(
        1, ge=1,
        description="只返回出现在至少 N 个 asset 的实体 (跨文档实体过滤)",
    ),
) -> list[ProjectEntity]:
    """列 project 下的规范化实体. asset_count 多的排前面."""
    return registry.list_entities(
        project_id,
        entity_type=type,  # type: ignore[arg-type]
        query=q,
        min_asset_count=min_assets,
    )


@router.get(
    "/entities/{entity_id}",
    response_model=ProjectEntity,
)
async def get_entity(entity_id: str) -> ProjectEntity:
    ent = registry.get_entity(entity_id)
    if ent is None:
        raise HTTPException(404, detail="Entity not found")
    return ent


@router.get(
    "/entities/{entity_id}/sources",
    response_model=list[EntitySourceItem],
)
async def get_entity_sources(entity_id: str) -> list[EntitySourceItem]:
    """该实体出现的所有 asset (合并到 asset 维度)."""
    if registry.get_entity(entity_id) is None:
        raise HTTPException(404, detail="Entity not found")

    def _lookup(aid: str) -> dict | None:
        a = svc.get_asset(aid)
        if a is None:
            return None
        return {"title": a.title, "type": a.type}

    return registry.get_sources(entity_id, asset_lookup=_lookup)


@router.get(
    "/assets/{asset_id}/nodes/{node_id}/entity",
    response_model=ProjectEntity,
)
async def get_node_entity(asset_id: str, node_id: str) -> ProjectEntity:
    """节点 → 它所属 project entity (前端 KG 节点 click 时调).

    返回 entity 含 source_refs (asset/chapter/node 三元组) 用于跨文档跳转.
    """
    ent = registry.get_entity_for_node(asset_id, node_id)
    if ent is None:
        raise HTTPException(404, detail="No entity for this node (asset 可能未跑 assess)")
    return ent


# ── T98 · merge / split endpoints ─────────────────────────────────


@router.post(
    "/entities/{entity_id}/merge",
    response_model=EntitiesMergedResult,
)
async def merge_entities(
    entity_id: str, body: MergeEntitiesRequest,
    user_id: str | None = Depends(get_current_user_id),
) -> EntitiesMergedResult:
    """v1.5 T98 / v1.6 T102 · 把 entity_id 合并到 body.target_id (source 被吞).

    T102: 执行前 record audit log (含 source 快照).
    """
    if entity_id == body.target_id:
        raise HTTPException(422, detail="Cannot merge entity into itself")
    src = registry.get_entity(entity_id)
    tgt = registry.get_entity(body.target_id)
    if src is None or tgt is None:
        raise HTTPException(404, detail="Entity not found")
    if src.project_id != tgt.project_id:
        raise HTTPException(422, detail="Cross-project merge not allowed")
    if src.type != tgt.type:
        raise HTTPException(422, detail="Cross-type merge not allowed")
    # T102: 记录前先快照
    audit_service.record_merge(
        project_id=src.project_id, source=src,
        target_id=tgt.id, target_label=tgt.label,
        actor_id=user_id,
    )
    merged = registry.merge_entities(entity_id, body.target_id)
    if merged is None:
        raise HTTPException(422, detail="Merge failed")
    return EntitiesMergedResult(target=merged)


@router.post(
    "/entities/{entity_id}/split",
    response_model=EntitiesSplitResult,
)
async def split_entity_node(
    entity_id: str, body: SplitNodeRequest,
    user_id: str | None = Depends(get_current_user_id),
) -> EntitiesSplitResult:
    """v1.5 T98 / v1.6 T102 · 从 entity 拆出一个 node ref 成新 entity.

    T102: 拆出后 record audit log; 可用 POST /entities/audit/:log_id/undo 撤销.
    """
    result = registry.split_node_to_new_entity(
        entity_id,
        asset_id=body.asset_id,
        node_id=body.node_id,
        new_label=body.new_label,
    )
    if result is None:
        if registry.get_entity(entity_id) is None:
            raise HTTPException(404, detail="Entity not found")
        raise HTTPException(
            422,
            detail="Split failed (ref 不存在 或 仅剩 1 ref 不可拆)",
        )
    src, new_ent = result
    # T102: 记录拆分供 undo
    from app.schemas.entity_registry import EntitySourceRef
    moved_ref = EntitySourceRef(
        asset_id=body.asset_id, chapter_id=src.source_refs[0].chapter_id if not src.source_refs else next(
            (r.chapter_id for r in new_ent.source_refs
             if r.asset_id == body.asset_id and r.node_id == body.node_id),
            new_ent.source_refs[0].chapter_id if new_ent.source_refs else "",
        ),
        node_id=body.node_id,
    )
    # 简化: 直接读 new_ent 的唯一 ref
    if new_ent.source_refs:
        moved_ref = new_ent.source_refs[0]
    audit_service.record_split(
        project_id=src.project_id,
        source_id=src.id,
        new_entity_id=new_ent.id,
        moved_node_ref=moved_ref,
        new_canonical=new_ent.canonical_label,
        actor_id=user_id,
    )
    return EntitiesSplitResult(source=src, new_entity=new_ent)


# ── T102 · audit log endpoints ────────────────────────────────────


@router.get(
    "/projects/{project_id}/entities/audit_log",
    response_model=list[EntityAuditLog],
)
async def list_entity_audit_log(
    project_id: str,
    op_type: Literal["merge", "split"] | None = Query(None),
    only_undoable: bool = Query(False, description="仅返回未 undo 的 split"),
    limit: int = Query(100, ge=1, le=500),
) -> list[EntityAuditLog]:
    return audit_service.list_logs(
        project_id, op_type=op_type, only_undoable=only_undoable, limit=limit,
    )


@router.post(
    "/entities/audit/{log_id}/undo",
    response_model=EntityAuditLog,
)
async def undo_entity_audit(
    log_id: str,
    user_id: str | None = Depends(get_current_user_id),
) -> EntityAuditLog:
    """v1.6 T102 · 撤销 split 操作 (merge undo 留 v1.7).

    422: log 不存在 / op_type=merge / 已 undone / state 已变.
    """
    log = audit_service.get_log(log_id)
    if log is None:
        raise HTTPException(404, detail="Audit log not found")
    if log.op_type != "split":
        raise HTTPException(
            422, detail="Only split operations can be undone in this version",
        )
    if log.undone:
        raise HTTPException(422, detail="Already undone")
    updated = audit_service.undo_split(log_id, actor_id=user_id)
    if updated is None:
        raise HTTPException(
            422,
            detail="Undo failed (state 已变, 比如 new entity 被改动或合并)",
        )
    return updated


# ── T99 · global (cross-project) entity endpoints ─────────────────


@router.post(
    "/entities/{entity_id}/publish_global",
    response_model=GlobalEntity,
)
async def publish_entity_to_global(
    entity_id: str,
    user_id: str | None = Depends(get_current_user_id),
) -> GlobalEntity:
    """v1.5 T99 · 把 project entity 发布到 global registry.

    同 (type, canonical) 全局已存在 → 自动 link 现有; 否则创建新 global.
    返回最终 GlobalEntity.
    """
    if registry.get_entity(entity_id) is None:
        raise HTTPException(404, detail="Project entity not found")
    gent = global_registry.publish_to_global(entity_id, actor_id=user_id)
    if gent is None:
        raise HTTPException(404, detail="Publish failed")
    return gent


@router.delete("/entities/{entity_id}/global", status_code=204)
async def unlink_project_entity_from_global(entity_id: str) -> None:
    """v1.5 T99 · 解除 project entity 与 global 的关联.

    最后一个 link 解除时, global entity 自动删除.
    """
    if registry.get_entity(entity_id) is None:
        raise HTTPException(404, detail="Project entity not found")
    ok = global_registry.unlink_project_entity(entity_id)
    if not ok:
        raise HTTPException(404, detail="Not linked to any global entity")


@router.get(
    "/entities/{entity_id}/global",
    response_model=GlobalEntity,
)
async def get_global_for_project_entity(entity_id: str) -> GlobalEntity:
    """v1.5 T99 · 反查 project entity → global. 未发布 → 404."""
    if registry.get_entity(entity_id) is None:
        raise HTTPException(404, detail="Project entity not found")
    gent = global_registry.get_global_for_project_entity(entity_id)
    if gent is None:
        raise HTTPException(404, detail="Not published to global")
    return gent


@router.get("/global/entities", response_model=list[GlobalEntity])
async def list_global_entities(
    type: Literal["person", "event", "concept", "artifact"] | None = Query(None),
    q: str | None = Query(None),
    min_projects: int = Query(
        1, ge=1,
        description="只返回横跨至少 N 个 project 的全局实体",
    ),
) -> list[GlobalEntity]:
    return global_registry.list_globals(
        entity_type=type,  # type: ignore[arg-type]
        query=q,
        min_projects=min_projects,
    )


@router.get(
    "/global/entities/{global_id}",
    response_model=GlobalEntity,
)
async def get_global_entity(global_id: str) -> GlobalEntity:
    gent = global_registry.get_global(global_id)
    if gent is None:
        raise HTTPException(404, detail="Global entity not found")
    return gent


@router.get(
    "/global/entities/{global_id}/projects",
    response_model=list[ProjectEntity],
)
async def list_linked_project_entities(global_id: str) -> list[ProjectEntity]:
    if global_registry.get_global(global_id) is None:
        raise HTTPException(404, detail="Global entity not found")
    return global_registry.get_linked_project_entities(global_id)
