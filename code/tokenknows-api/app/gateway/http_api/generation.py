"""POST /assets/generate + GET /assets/:id + 进度 + SSE 流.

设计依据:
    - TDD §6.1 (API 端点)
    - Architecture.md §4.3.3 (5 阶段流水线)
    - TaskTechDesign T06 (生成 + polling/SSE 协同)
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from pydantic import BaseModel

from app.schemas.asset import Asset, Chapter
from app.schemas.generation import (
    GenerateAssetRequest,
    GenerationProgress,
)
from app.services import generation_service as svc

router = APIRouter()


class PaginatedAssets(BaseModel):
    """前端 useInfiniteQuery 期待的分页响应格式 (与 MSW mock 一致)."""

    data: list[Asset]
    meta: dict


# ─── 触发生成 ─────────────────────────────────────────────────────


@router.post(
    "/projects/{project_id}/assets/generate",
    response_model=Asset,
    status_code=202,
)
async def generate_asset(project_id: str, req: GenerateAssetRequest) -> Asset:
    """触发文档生成. 立即返回 (status=generating), 5 阶段后台跑."""
    return await svc.start_generation(project_id, req)


# ─── 项目级 asset 列表 (MVP 仅返回内存里的) ──────────────────────


@router.get(
    "/projects/{project_id}/assets",
    response_model=PaginatedAssets,
)
async def list_project_assets(project_id: str) -> PaginatedAssets:
    """前端 useAssets 是 useInfiniteQuery, 期待 { data, meta: { cursor, has_more } }.

    MVP 内存版无真正分页, 一次返回所有.
    """
    items = svc.list_assets(project_id)
    return PaginatedAssets(
        data=items,
        meta={"total": len(items), "cursor": None, "has_more": False},
    )


# ─── 单 asset 详情 ────────────────────────────────────────────────


@router.get("/assets/{asset_id}", response_model=Asset)
async def get_asset(asset_id: str) -> Asset:
    asset = svc.get_asset(asset_id)
    if asset is None:
        raise HTTPException(404, detail="Asset not found")
    return asset


@router.get("/assets/{asset_id}/chapters", response_model=list[Chapter])
async def list_chapters(asset_id: str) -> list[Chapter]:
    if svc.get_asset(asset_id) is None:
        raise HTTPException(404, detail="Asset not found")
    return svc.list_chapters(asset_id)


# ─── 删除 / 克隆 (T05 列表卡更多菜单) ────────────────────────────


@router.delete("/assets/{asset_id}", status_code=204)
async def delete_asset(asset_id: str) -> None:
    """硬删 (MVP 内存; 生产换软删 status=archived)."""
    if not svc.delete_asset(asset_id):
        raise HTTPException(404, detail="Asset not found")
    return None


@router.post("/assets/{asset_id}/clone", response_model=Asset, status_code=201)
async def clone_asset(asset_id: str) -> Asset:
    """克隆为新草稿 (TaskTechDesign T05: '复制'是克隆 asset 而非复制链接)."""
    cloned = svc.clone_asset(asset_id)
    if cloned is None:
        raise HTTPException(404, detail="Asset not found")
    return cloned


# ─── 进度 (polling) ──────────────────────────────────────────────


@router.get(
    "/assets/{asset_id}/generation/status",
    response_model=GenerationProgress,
)
async def get_progress(asset_id: str) -> GenerationProgress:
    progress = svc.get_progress(asset_id)
    if progress is None:
        raise HTTPException(404, detail="Asset not found or not generated yet")
    return progress


# ─── SSE 流 (W4D17 前端切换) ──────────────────────────────────────


@router.get("/assets/{asset_id}/generation/stream")
async def stream_progress(asset_id: str, request: Request) -> StreamingResponse:
    """SSE 推送 5 阶段进度.

    事件类型: stage_started / stage_completed / chapter_completed / done / failed
    断线重连由前端 EventSource 自动处理.
    """
    if svc.get_progress(asset_id) is None:
        raise HTTPException(404, detail="Asset not found")

    queue = await svc.subscribe_sse(asset_id)

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            # 推一次当前快照, 让晚连的客户端能立刻看到当前状态
            snapshot = svc.get_progress(asset_id)
            if snapshot:
                yield _sse_format(
                    event="snapshot",
                    data=snapshot.model_dump_json(),
                )

            while True:
                # 客户端断开 → 退出循环
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # 心跳 - 防 nginx / Vite proxy 掐连接
                    yield b": heartbeat\n\n"
                    continue

                yield _sse_format(
                    event=event.event,
                    data=event.model_dump_json(),
                )

                if event.event in ("done", "failed"):
                    break
        finally:
            await svc.cleanup_sse(asset_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 关 nginx buffering
            "Connection": "keep-alive",
        },
    )


def _sse_format(*, event: str, data: str) -> bytes:
    """格式化 SSE 行."""
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")
