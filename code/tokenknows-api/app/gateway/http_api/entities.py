"""v1.3.1 T96 · GET /projects/:pid/entities + GET /entities/:eid + sources.

跨 KG asset 的 project 级实体规范化 (人/事件/概念/产物).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.schemas.entity_registry import EntitySourceItem, ProjectEntity
from app.services import generation_service as svc
from app.services.knowledge_graph import entity_registry as registry

router = APIRouter()


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
