"""文档生成 5 阶段流水线 (MVP 骨架版 · 不调 LLM).

设计依据 Architecture.md §4.3.3 数据流 3:
    ① collect:    候选 ValueSegment (按时间窗 + filter + trust_score TOP-N)
    ② outline:    主题聚类 + 大纲 (LLM call 1, 结构化输出 chapters[])
    ③ content:    章节正文生成 (LLM call × N, 要求结构化引用)
    ④ evidence:   结构化引用回填; 失败回退 TF-IDF / pgvector cosine
    ⑤ assess:     自评卡 (coverage / citation_density / slop_score / similarity)
    每阶段 publish Redis → 前端 SSE 收到进度.

MVP 简化:
    - 不调真 LLM (每阶段 asyncio.sleep 1-2s 模拟)
    - 不连 Postgres (内存 dict 存 asset / chapter / progress)
    - 不连 Redis (用 asyncio.Queue 实现 SSE fan-out)
    - 不连 Celery (用 asyncio.create_task 后台跑)

下次接入真 LLM 时, 替换 _stage_*() 函数内的 sleep 为 llm_gateway 调用.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config.logging import logger
from app.config.settings import get_settings
from app.schemas.asset import (
    Asset,
    AssetMetrics,
    AssetType,
    Chapter,
    ChapterGeneratedBy,
)
from app.schemas.generation import (
    GenerateAssetRequest,
    GenerationProgress,
    SseEvent,
    StageName,
    StageStatus,
)

# ─── In-memory state (MVP only; 生产换 Postgres + Redis Streams) ─────

_assets: dict[str, Asset] = {}
_chapters: dict[str, list[Chapter]] = {}
_progress: dict[str, GenerationProgress] = {}
_sse_queues: dict[str, list[asyncio.Queue]] = {}
_state_lock = asyncio.Lock()


# 标题模板 (替代真 LLM 时的占位)
_TITLE_TEMPLATES: dict[AssetType, str] = {
    "weekly_report": "周报 · {window}",
    "tech_design": "技术方案 · 范围 = {window}",
    "adr": "ADR · 待填写决策主题",
    "incident": "问题复盘 · 时间窗 {window}",
}

# 每类文档的章节大纲 (替代 outline LLM 调用)
_OUTLINE_TEMPLATES: dict[AssetType, list[str]] = {
    "weekly_report": [
        "本周进展",
        "Bug 与解决",
        "关键决策",
        "风险与阻塞",
        "下周计划",
    ],
    "tech_design": [
        "背景",
        "目标",
        "设计思路",
        "关键决策",
        "风险与取舍",
        "实施计划",
    ],
    "adr": ["上下文", "决策内容", "备选方案", "后果", "状态"],
    "incident": [
        "现象",
        "影响范围",
        "根因",
        "解决过程",
        "改进措施",
        "时间线",
    ],
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _initial_progress(asset_id: str) -> GenerationProgress:
    now = _now()
    stage_names: list[StageName] = ["collect", "outline", "content", "evidence", "assess"]
    return GenerationProgress(
        asset_id=asset_id,
        overall_status="pending",
        current_stage=None,
        stages=[
            StageStatus(name=n, status="pending") for n in stage_names
        ],
        started_at=now,
        updated_at=now,
    )


def _stage_index(progress: GenerationProgress, name: StageName) -> int:
    for i, s in enumerate(progress.stages):
        if s.name == name:
            return i
    raise ValueError(f"Unknown stage: {name}")


# ─── SSE pub/sub (内存 fan-out) ──────────────────────────────────


async def _publish_event(asset_id: str, event: SseEvent) -> None:
    """向所有订阅该 asset 的 SSE queue 推一个事件."""
    queues = _sse_queues.get(asset_id, [])
    for q in queues:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            # 容忍单个客户端落后 - 不阻塞其它
            logger.warning("sse_queue_full", asset_id=asset_id)


async def subscribe_sse(asset_id: str) -> asyncio.Queue:
    """SSE 端点用. 返回一个 queue, 取消订阅由调用方负责 (cleanup_sse)."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    async with _state_lock:
        _sse_queues.setdefault(asset_id, []).append(queue)
    return queue


async def cleanup_sse(asset_id: str, queue: asyncio.Queue) -> None:
    async with _state_lock:
        if asset_id in _sse_queues:
            _sse_queues[asset_id] = [q for q in _sse_queues[asset_id] if q is not queue]


# ─── 流水线 5 阶段 (MVP: asyncio.sleep 模拟; 后续接 llm_gateway) ──


async def _run_stage(
    asset_id: str,
    stage: StageName,
    work: Any,  # 协程 - 返回 metadata dict
) -> None:
    """通用阶段执行器: 设 running → 跑 work → 设 done/failed + 发 SSE."""
    progress = _progress[asset_id]
    idx = _stage_index(progress, stage)
    now = _now()

    progress.stages[idx].status = "running"
    progress.stages[idx].started_at = now
    progress.current_stage = stage
    progress.overall_status = "running"
    progress.updated_at = now

    await _publish_event(
        asset_id,
        SseEvent(event="stage_started", asset_id=asset_id, stage=stage, ts=now),
    )

    try:
        metadata = await work
        end = _now()
        progress.stages[idx].status = "done"
        progress.stages[idx].completed_at = end
        progress.stages[idx].metadata = metadata or {}
        progress.updated_at = end
        await _publish_event(
            asset_id,
            SseEvent(
                event="stage_completed",
                asset_id=asset_id,
                stage=stage,
                payload=metadata or {},
                ts=end,
            ),
        )
    except Exception as exc:
        end = _now()
        progress.stages[idx].status = "failed"
        progress.stages[idx].completed_at = end
        progress.stages[idx].error = str(exc)
        progress.overall_status = "failed"
        progress.error = str(exc)
        progress.updated_at = end
        await _publish_event(
            asset_id,
            SseEvent(
                event="failed",
                asset_id=asset_id,
                stage=stage,
                payload={"error": str(exc)},
                ts=end,
            ),
        )
        logger.error("generation_stage_failed", asset_id=asset_id, stage=stage, error=str(exc))
        raise


async def _stage_collect(asset_id: str, req: GenerateAssetRequest) -> dict:
    """阶段 1 · 按时间窗 + filter 从事件库选 TOP-N 候选.

    MVP 占位: 假装拿到 50 个候选 trust_score 平均 0.72.
    生产: 查 Postgres events + value_segments, ORDER BY trust_score DESC LIMIT 50.
    """
    await asyncio.sleep(0.8)
    return {
        "candidates_count": 50,
        "trust_score_avg": 0.72,
        "time_window": req.time_window,
    }


async def _stage_outline(asset_id: str, req: GenerateAssetRequest) -> dict:
    """阶段 2 · 主题聚类 + 大纲.

    MVP 占位: 用 _OUTLINE_TEMPLATES.
    生产: llm_gateway.generate(task="outline", json_mode=True, structured output).
    """
    await asyncio.sleep(1.2)
    outline = _OUTLINE_TEMPLATES[req.type]
    return {"chapters_total": len(outline), "titles": outline}


async def _stage_content(asset_id: str, req: GenerateAssetRequest) -> dict:
    """阶段 3 · 章节正文生成 (per-chapter LLM call).

    MVP 占位: 每章 sleep 0.5s + 写一段 placeholder markdown.
    生产: 每章一次 llm_gateway.generate(task=req.type, messages=[...]).
    """
    settings = get_settings()
    asset = _assets[asset_id]
    outline = _OUTLINE_TEMPLATES[req.type]
    provider = req.provider_override or settings.task_provider(req.type)
    model = req.model_override or settings.task_model(req.type)

    chapters: list[Chapter] = []
    for idx, title in enumerate(outline):
        await asyncio.sleep(0.5)  # 模拟单章 LLM 调用
        chapters.append(
            Chapter(
                id=f"chapter-{uuid4().hex[:8]}",
                asset_id=asset_id,
                asset_version=1,
                order_index=idx,
                title=title,
                content=_placeholder_content(title, req.type),
                generated_by=ChapterGeneratedBy(
                    model=model,
                    provider=provider,
                    latency_ms=500,
                    prompt_tokens=0,
                    completion_tokens=0,
                ),
            )
        )
        # 推 chapter_completed 事件 - 前端可以增量渲染
        await _publish_event(
            asset_id,
            SseEvent(
                event="chapter_completed",
                asset_id=asset_id,
                stage="content",
                payload={"order_index": idx, "title": title, "total": len(outline)},
                ts=_now(),
            ),
        )

    _chapters[asset_id] = chapters
    return {
        "chapters_completed": len(chapters),
        "provider_used": provider,
        "model_used": model,
    }


async def _stage_evidence(asset_id: str, req: GenerateAssetRequest) -> dict:
    """阶段 4 · 证据链回填.

    MVP 占位: 假装回填 18 条 evidence.
    生产: 解析阶段 3 LLM 返回的结构化 spans→event_ids; 失败回退 TF-IDF.
    """
    await asyncio.sleep(0.8)
    return {"evidence_total": 18, "evidence_stale": 0, "fallback_used": False}


async def _stage_assess(asset_id: str, req: GenerateAssetRequest) -> dict:
    """阶段 5 · 自评卡 (coverage / citation_density / slop / similarity).

    MVP 占位: 随机化但合理的数值.
    生产: 计算 chapter↔event 引用覆盖比 / TF-IDF 空话检测 / pgvector 相似度.
    """
    import random
    await asyncio.sleep(0.6)
    metrics = AssetMetrics(
        coverage=round(0.70 + random.random() * 0.25, 3),
        citation_density=round(0.55 + random.random() * 0.35, 3),
        slop_score=round(random.random() * 0.20, 3),
        similarity=round(random.random() * 0.40, 3),
    )
    # 写回 asset
    asset = _assets[asset_id]
    asset.metrics = metrics
    asset.status = "draft"
    asset.current_version = 1
    asset.updated_at = _now()
    return metrics.model_dump()


def _placeholder_content(title: str, asset_type: AssetType) -> str:
    """章节 markdown 占位 (替代真 LLM 输出)."""
    return (
        f"## {title}\n\n"
        f"_本章节为骨架占位, 待真实 LLM 调用接入后替换._\n\n"
        f"- 文档类型: `{asset_type}`\n"
        f"- 生成阶段: content (stage 3)\n"
        f"- 此处会包含 LLM 基于候选 ValueSegment 生成的正文段落,\n"
        f"  每段附 `[1] [2] [3]` 形式的证据角标 (阶段 4 回填).\n\n"
        f"> ⚠ 待真 LLM 调用接通后, 此占位由 prompt 中的指令引导模型生成具体内容."
    )


# ─── 公开 API ─────────────────────────────────────────────────────


async def start_generation(
    project_id: str,
    req: GenerateAssetRequest,
    user_id: str | None = None,
) -> Asset:
    """触发文档生成. 立即返回 Asset (status=generating), 后台跑 5 阶段."""
    settings = get_settings()
    asset_id = f"asset-{uuid4().hex[:10]}"
    now = _now()
    asset = Asset(
        id=asset_id,
        project_id=project_id,
        type=req.type,
        title=_TITLE_TEMPLATES[req.type].format(window=req.time_window),
        status="generating",
        current_version=0,
        template_id=f"tpl-{req.type}",
        created_by=user_id or "anonymous",
        created_at=now,
        updated_at=now,
    )

    async with _state_lock:
        _assets[asset_id] = asset
        _chapters[asset_id] = []
        _progress[asset_id] = _initial_progress(asset_id)
        # 记录路由信息
        _progress[asset_id].primary_provider = (
            req.provider_override or settings.task_provider(req.type)
        )
        _progress[asset_id].primary_model = (
            req.model_override or settings.task_model(req.type)
        )

    # 后台跑流水线
    asyncio.create_task(_run_pipeline(asset_id, req))
    return asset


async def _run_pipeline(asset_id: str, req: GenerateAssetRequest) -> None:
    """5 阶段顺序执行. 失败短路."""
    try:
        await _run_stage(asset_id, "collect", _stage_collect(asset_id, req))
        await _run_stage(asset_id, "outline", _stage_outline(asset_id, req))
        await _run_stage(asset_id, "content", _stage_content(asset_id, req))
        await _run_stage(asset_id, "evidence", _stage_evidence(asset_id, req))
        await _run_stage(asset_id, "assess", _stage_assess(asset_id, req))

        progress = _progress[asset_id]
        progress.overall_status = "done"
        progress.current_stage = None
        progress.updated_at = _now()
        await _publish_event(
            asset_id,
            SseEvent(event="done", asset_id=asset_id, ts=_now(),
                     payload={"chapters_total": len(_chapters[asset_id])}),
        )
        logger.info(
            "generation_done",
            asset_id=asset_id,
            chapters=len(_chapters[asset_id]),
        )
    except Exception as exc:
        logger.error("generation_pipeline_failed", asset_id=asset_id, error=str(exc))
        # _run_stage 已经写入失败状态


# ─── 查询 API ─────────────────────────────────────────────────────


def get_asset(asset_id: str) -> Asset | None:
    return _assets.get(asset_id)


def list_chapters(asset_id: str) -> list[Chapter]:
    return _chapters.get(asset_id, [])


def get_progress(asset_id: str) -> GenerationProgress | None:
    return _progress.get(asset_id)


def list_assets(project_id: str) -> list[Asset]:
    return [a for a in _assets.values() if a.project_id == project_id]


def delete_asset(asset_id: str) -> bool:
    """硬删 (MVP 内存; 生产换软删 status=archived)."""
    if asset_id not in _assets:
        return False
    _assets.pop(asset_id, None)
    _chapters.pop(asset_id, None)
    _progress.pop(asset_id, None)
    _sse_queues.pop(asset_id, None)
    return True


def clone_asset(asset_id: str) -> Asset | None:
    """复制 asset → 新草稿. 同步复制 chapters (TaskTechDesign T05 决策)."""
    src = _assets.get(asset_id)
    if src is None:
        return None
    new_id = f"asset-{uuid4().hex[:10]}"
    now = _now()
    cloned = src.model_copy(
        update={
            "id": new_id,
            "title": f"{src.title} (副本)",
            "status": "draft",
            "current_version": 1,
            "approval_state": "pending",
            "redaction_state": "any_unresolved",
            "created_at": now,
            "updated_at": now,
        }
    )
    _assets[new_id] = cloned
    # 同步克隆章节 (新 chapter id)
    src_chapters = _chapters.get(asset_id, [])
    _chapters[new_id] = [
        c.model_copy(
            update={
                "id": f"chapter-{uuid4().hex[:8]}",
                "asset_id": new_id,
                "approval_state": "pending",
            }
        )
        for c in src_chapters
    ]
    return cloned
