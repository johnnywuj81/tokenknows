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

from app.schemas.asset import Asset, Chapter, Evidence, PublishRecord, RedactionScanJob
from app.schemas.generation import (
    GenerateAssetRequest,
    GenerationProgress,
)
from app.services import generation_service as svc

router = APIRouter()


class ChapterPatchRequest(BaseModel):
    """T06 Phase 2 自动保存请求."""

    content: str


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


@router.patch("/assets/{asset_id}/chapters/{chapter_id}", response_model=Chapter)
async def patch_chapter(
    asset_id: str, chapter_id: str, body: ChapterPatchRequest
) -> Chapter:
    """更新章节内容 (T06 自动保存). 返回 server-side 结果让前端 reconcile."""
    updated = svc.update_chapter_content(asset_id, chapter_id, body.content)
    if updated is None:
        raise HTTPException(404, detail="Chapter not found")
    return updated


@router.get(
    "/assets/{asset_id}/chapters/{chapter_id}/evidence",
    response_model=list[Evidence],
)
async def list_chapter_evidence(asset_id: str, chapter_id: str) -> list[Evidence]:
    """T07 · 一次性返回本章所有 Evidence (含 event_preview, 抽屉切换不再 fetch)."""
    if svc.get_asset(asset_id) is None:
        raise HTTPException(404, detail="Asset not found")
    return svc.list_chapter_evidence(asset_id, chapter_id)


class RegenerateChapterRequest(BaseModel):
    """T08 · 重生成单章节请求."""

    instruction: str
    model: str | None = None       # e.g. "minimax-m2:cloud" (override task default)
    provider: str | None = None    # e.g. "ollama" / "anthropic" (override task default)


class RejectChapterRequest(BaseModel):
    """T09 · 章节退回请求."""

    reason: str


# ─── T09 · 审批 endpoints ────────────────────────────────────────


@router.post(
    "/assets/{asset_id}/submit",
    response_model=Asset,
)
async def submit_asset(asset_id: str) -> Asset:
    """T09 · 作者提交审批 → status=in_review, 章节 approval_state 重置."""
    asset = svc.submit_asset_for_review(asset_id)
    if asset is None:
        raise HTTPException(404, detail="Asset not found")
    return asset


@router.post(
    "/assets/{asset_id}/chapters/{chapter_id}/approve",
    response_model=Chapter,
)
async def approve_chapter(asset_id: str, chapter_id: str) -> Chapter:
    """T09 · 章节通过. 全部通过时自动升 asset.status=approved."""
    if svc.get_asset(asset_id) is None:
        raise HTTPException(404, detail="Asset not found")
    chapter = svc.approve_chapter(asset_id, chapter_id)
    if chapter is None:
        raise HTTPException(404, detail="Chapter not found")
    return chapter


@router.post(
    "/assets/{asset_id}/chapters/{chapter_id}/reject",
    response_model=Chapter,
)
async def reject_chapter(
    asset_id: str, chapter_id: str, body: RejectChapterRequest
) -> Chapter:
    """T09 · 章节退回 (必填 reason). asset.approval_state 立即变 'rejected'."""
    if svc.get_asset(asset_id) is None:
        raise HTTPException(404, detail="Asset not found")
    if not body.reason.strip():
        raise HTTPException(422, detail="退回原因不能为空")
    chapter = svc.reject_chapter(asset_id, chapter_id, body.reason.strip())
    if chapter is None:
        raise HTTPException(404, detail="Chapter not found")
    return chapter


# ─── T10 · 脱敏 endpoints ────────────────────────────────────────


class ConfirmRedactionRequest(BaseModel):
    item_ids: list[str]


class ExemptRedactionRequest(BaseModel):
    item_id: str
    reason: str


@router.post(
    "/assets/{asset_id}/redaction/scan",
    response_model=RedactionScanJob,
)
async def scan_redaction(asset_id: str) -> RedactionScanJob:
    """T10 · 同步扫描章节内容找敏感内容 (MVP 正则; 生产异步 + LLM 兜底)."""
    if svc.get_asset(asset_id) is None:
        raise HTTPException(404, detail="Asset not found")
    job = svc.scan_redaction(asset_id)
    if job is None:
        raise HTTPException(404, detail="No chapters to scan")
    return job


@router.get(
    "/assets/{asset_id}/redaction/scan",
    response_model=RedactionScanJob,
)
async def get_redaction_scan(asset_id: str) -> RedactionScanJob:
    """获取最近一次扫描结果 (404 表示尚未扫描)."""
    if svc.get_asset(asset_id) is None:
        raise HTTPException(404, detail="Asset not found")
    job = svc.get_redaction_job(asset_id)
    if job is None:
        raise HTTPException(404, detail="尚未扫描, 请先调用 POST /redaction/scan")
    return job


@router.post(
    "/assets/{asset_id}/redaction/confirm",
    response_model=RedactionScanJob,
)
async def confirm_redaction(
    asset_id: str, body: ConfirmRedactionRequest
) -> RedactionScanJob:
    """T10 · 批量确认 (status=confirmed)."""
    if svc.get_asset(asset_id) is None:
        raise HTTPException(404, detail="Asset not found")
    job = svc.confirm_redaction(asset_id, body.item_ids)
    if job is None:
        raise HTTPException(404, detail="尚未扫描")
    return job


@router.post(
    "/assets/{asset_id}/redaction/exempt",
    response_model=RedactionScanJob,
)
async def exempt_redaction(
    asset_id: str, body: ExemptRedactionRequest
) -> RedactionScanJob:
    """T10 · 单项豁免 (必填 reason)."""
    if svc.get_asset(asset_id) is None:
        raise HTTPException(404, detail="Asset not found")
    if not body.reason.strip():
        raise HTTPException(422, detail="豁免理由不能为空")
    job = svc.exempt_redaction(asset_id, body.item_id, body.reason.strip())
    if job is None:
        raise HTTPException(404, detail="尚未扫描")
    return job


# ─── T11/T12 · 发布 ────────────────────────────────────────────


class PublishRequest(BaseModel):
    """T11 · 发布请求."""

    destinations: list[str]    # ['internal', 'public_link', 'export_md']
    publish_mode: str          # 'full' / 'summary_with_backlink'
    visibility: str | None = None  # 公开链接时: 'team' / 'public'


@router.post(
    "/assets/{asset_id}/publish",
    response_model=list[PublishRecord],
    status_code=201,
)
async def publish_asset(asset_id: str, body: PublishRequest) -> list[PublishRecord]:
    """T11 · 多渠道发布. 返回每个渠道的 PublishRecord."""
    if svc.get_asset(asset_id) is None:
        raise HTTPException(404, detail="Asset not found")
    try:
        return svc.publish_asset(
            asset_id=asset_id,
            destinations=body.destinations,
            publish_mode=body.publish_mode,
            visibility=body.visibility,
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router.get(
    "/publish-records/{record_id}",
    response_model=PublishRecord,
)
async def get_publish_record(record_id: str) -> PublishRecord:
    """T12 · 单条发布记录详情 (回执页)."""
    record = svc.get_publish_record(record_id)
    if record is None:
        raise HTTPException(404, detail="Publish record not found")
    return record


@router.get(
    "/assets/{asset_id}/publish-records",
    response_model=list[PublishRecord],
)
async def list_asset_publish_records(asset_id: str) -> list[PublishRecord]:
    """T12 · 文档的发布历史 (按时间倒序)."""
    if svc.get_asset(asset_id) is None:
        raise HTTPException(404, detail="Asset not found")
    records = svc.list_publish_records_for_asset(asset_id)
    return sorted(records, key=lambda r: r.published_at, reverse=True)


@router.post(
    "/assets/{asset_id}/chapters/{chapter_id}/regenerate",
    response_model=Chapter,
)
async def regenerate_chapter(
    asset_id: str,
    chapter_id: str,
    body: RegenerateChapterRequest,
) -> Chapter:
    """T08 · 用用户指令重生成本章节. 同步等 LLM 完成后返回新章节.

    前端 mutation 流程:
      isPending → ChapterBlock regenerating=true (锁编辑)
      onSuccess → invalidateQueries chapters + evidence
    """
    if svc.get_asset(asset_id) is None:
        raise HTTPException(404, detail="Asset not found")
    try:
        updated = await svc.regenerate_chapter(
            asset_id=asset_id,
            chapter_id=chapter_id,
            instruction=body.instruction.strip(),
            model_override=body.model,
            provider_override=body.provider,
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except Exception as exc:  # LLM 调用全失败 / circuit open
        raise HTTPException(503, detail=f"LLM 重生成失败: {exc}") from exc
    if updated is None:
        raise HTTPException(404, detail="Chapter not found")
    return updated


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
