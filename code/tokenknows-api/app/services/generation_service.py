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
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.config.logging import logger
from app.config.settings import get_settings
from app.llm_gateway import LLMMessage, LLMOptions, get_router
from app.persistence import get_db
from app.schemas.asset import (
    Asset,
    AssetMetrics,
    AssetType,
    Chapter,
    ChapterGeneratedBy,
    Evidence,
    EvidencePreview,
    PublishRecord,
    RedactionItem,
    RedactionScanJob,
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
# T07: chapter_id → List[Evidence]
_evidence_by_chapter: dict[str, list[Evidence]] = {}
# T10: asset_id → RedactionScanJob
_redaction_jobs: dict[str, RedactionScanJob] = {}
# T11/T12: publish_record_id → PublishRecord
_publish_records: dict[str, PublishRecord] = {}
_state_lock = asyncio.Lock()


# ─── P1 · SQLite 持久化 helper ────────────────────────────────────


def _persist_asset(asset_id: str) -> None:
    """把 asset + progress + chapters + evidence 写入 SQLite.

    在每个 mutation 之后调. dict 是读 cache, SQLite 是真理之源.
    重启 _bootstrap_from_db() 全量重建 dict.
    """
    asset = _assets.get(asset_id)
    if asset is None:
        return
    db = get_db()
    db.upsert_asset(
        asset_id=asset.id,
        project_id=asset.project_id,
        status=asset.status,
        asset_type=asset.type,
        updated_at=asset.updated_at.isoformat(),
        json_str=asset.model_dump_json(),
    )

    progress = _progress.get(asset_id)
    if progress is not None:
        db.upsert_progress(
            asset_id=asset_id,
            overall=progress.overall_status,
            json_str=progress.model_dump_json(),
        )

    chapters = _chapters.get(asset_id, [])
    db.replace_chapters(
        asset_id,
        [(c.id, c.order_index, c.model_dump_json()) for c in chapters],
    )

    # evidence (按 chapter)
    for ch in chapters:
        ev_list = _evidence_by_chapter.get(ch.id, [])
        db.replace_evidence(
            ch.id,
            [(e.id, e.model_dump_json()) for e in ev_list],
        )


def _persist_redaction_job(asset_id: str) -> None:
    job = _redaction_jobs.get(asset_id)
    if job is None:
        return
    get_db().upsert_redaction_job(asset_id, job.model_dump_json())


def _persist_publish_record(record_id: str) -> None:
    record = _publish_records.get(record_id)
    if record is None:
        return
    get_db().upsert_publish_record(
        record_id=record_id,
        asset_id=record.asset_id,
        published_at=record.published_at,
        json_str=record.model_dump_json(),
    )


def _bootstrap_from_db() -> None:
    """启动时从 SQLite 加载所有状态. main.py @app.on_event('startup') 调."""
    db = get_db()

    # Assets
    for raw in db.load_all_assets():
        asset = Asset.model_validate(raw)
        _assets[asset.id] = asset

        # Progress
        prog_raw = db.load_progress(asset.id)
        if prog_raw is not None:
            _progress[asset.id] = GenerationProgress.model_validate(prog_raw)

        # Chapters
        chap_raws = db.load_chapters_for_asset(asset.id)
        chapters = [Chapter.model_validate(r) for r in chap_raws]
        _chapters[asset.id] = chapters

    # Evidence (一次查全表更快)
    ev_by_chapter = db.load_all_evidence()
    for chapter_id, raws in ev_by_chapter.items():
        _evidence_by_chapter[chapter_id] = [Evidence.model_validate(r) for r in raws]

    # Redaction jobs
    for asset_id, raw in db.load_all_redaction_jobs().items():
        _redaction_jobs[asset_id] = RedactionScanJob.model_validate(raw)

    # Publish records
    for raw in db.load_all_publish_records():
        record = PublishRecord.model_validate(raw)
        _publish_records[record.id] = record

    stats = db.stats()
    logger.info(
        "persistence_loaded",
        assets=stats["assets"],
        chapters=stats["chapters"],
        evidence=stats["evidence"],
        publish_records=stats["publish_records"],
    )


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
        # P1 持久化: 每阶段完成 → SQLite
        _persist_asset(asset_id)
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
        _persist_asset(asset_id)
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
    """阶段 2 · 主题聚类 + 大纲 (★ 真 LLM 调用).

    走 llm_gateway → router.generate (三层出域门禁 + CircuitBreaker + egress_log).
    JSON mode 严格输出 {chapters: [titles...]}.
    失败回退到 _OUTLINE_TEMPLATES 保证 demo 不挂.
    """
    asset = _assets[asset_id]
    type_label = {
        "weekly_report": "项目周报",
        "tech_design": "技术方案",
        "adr": "ADR 架构决策记录",
        "incident": "问题复盘报告",
    }[req.type]
    fallback = _OUTLINE_TEMPLATES[req.type]

    system_prompt = (
        "你是 AI 研发知识资产平台的文档大纲生成器。严格按 JSON schema 输出, 不要任何额外文字。\n"
        'JSON schema: {"chapters": ["章节1", "章节2", ...]}\n'
        "约束: 章节标题简洁(≤8 字符), 数量 5-7 个, 顺序符合该文档类型的标准结构。"
    )
    user_prompt = (
        f"为「{type_label}」文档生成章节大纲。\n"
        f"时间范围: {req.time_window}\n"
        f"参考标准结构 (你可微调以贴合本次主题): {' / '.join(fallback)}"
    )

    router = await get_router()
    try:
        response = await router.generate(
            task=req.type,
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            options=LLMOptions(
                temperature=0.3,
                max_tokens=400,
                json_mode=True,
                timeout_seconds=60,
            ),
            project_id=asset.project_id,
        )
        parsed = json.loads(response.text)
        outline = parsed.get("chapters", [])
        if not isinstance(outline, list) or len(outline) < 3:
            raise ValueError(f"LLM 返回大纲不合理: {outline!r}")
        logger.info(
            "outline_llm_success",
            asset_id=asset_id,
            provider=response.provider,
            model=response.model_used,
            chapters=len(outline),
            tokens=response.usage,
            fallback_used=response.fallback_used,
        )
        return {
            "chapters_total": len(outline),
            "titles": outline,
            "provider_used": response.provider,
            "model_used": response.model_used,
            "tokens": response.usage,
            "fallback_used": response.fallback_used,
        }
    except Exception as exc:
        logger.warning(
            "outline_llm_failed_fallback",
            asset_id=asset_id,
            error=str(exc),
        )
        # 不抛 - 用 fallback 大纲让流水线继续
        return {
            "chapters_total": len(fallback),
            "titles": fallback,
            "llm_fallback_to_template": True,
            "llm_error": str(exc),
        }


async def _stage_content(asset_id: str, req: GenerateAssetRequest) -> dict:
    """阶段 3 · 章节正文生成 (per-chapter LLM call · ★ 真 LLM).

    每章一次 router.generate(task=req.type, ...) 并行执行 (asyncio.gather).
    失败的章节回退到 _placeholder_content 保证 demo 不挂.

    titles 优先从 outline 阶段产出读 (LLM 真生成的标题), 没有则 fallback 模板.
    """
    settings = get_settings()
    progress = _progress[asset_id]
    outline_stage = next(
        (s for s in progress.stages if s.name == "outline"), None
    )
    outline = (
        outline_stage.metadata.get("titles") if outline_stage else None
    ) or _OUTLINE_TEMPLATES[req.type]
    provider = req.provider_override or settings.task_provider(req.type)
    model = req.model_override or settings.task_model(req.type)
    asset = _assets[asset_id]

    # 并行调 LLM 生章节 - 收集 (content, latency_ms, usage, fallback_used)
    async def gen_one(idx: int, title: str) -> tuple[int, str, str, dict, bool, int]:
        result = await _call_chapter_llm(
            asset.type, title, req.time_window, asset.project_id, provider, model
        )
        # 推增量 SSE
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
        return (idx, title, result["content"], result["usage"], result["fallback_used"], result["latency_ms"])

    results = await asyncio.gather(*(gen_one(i, t) for i, t in enumerate(outline)))
    results.sort(key=lambda x: x[0])

    chapters: list[Chapter] = []
    for idx, title, content, usage, fb_used, latency in results:
        chapters.append(
            Chapter(
                id=f"chapter-{uuid4().hex[:8]}",
                asset_id=asset_id,
                asset_version=1,
                order_index=idx,
                title=title,
                content=content,
                generated_by=ChapterGeneratedBy(
                    model=model,
                    provider=provider,
                    latency_ms=latency,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                ),
            )
        )

    _chapters[asset_id] = chapters
    return {
        "chapters_completed": len(chapters),
        "provider_used": provider,
        "model_used": model,
        "fallback_used_count": sum(1 for r in results if r[4]),
    }


async def _call_chapter_llm(
    asset_type: AssetType,
    title: str,
    time_window: str,
    project_id: str,
    provider: str,
    model: str,
) -> dict[str, Any]:
    """单章节 LLM 调用 · 失败回退到 placeholder content.

    返回 {content, usage, fallback_used, latency_ms}.
    """
    type_label = {
        "weekly_report": "项目周报",
        "tech_design": "技术方案",
        "adr": "ADR 架构决策记录",
        "incident": "问题复盘报告",
    }[asset_type]

    system_prompt = (
        "你是 AI 研发知识资产平台的章节生成器。根据章节标题生成 200-400 字的"
        "markdown 草稿, 风格客观、要点清晰。允许包含 `[1] [2] [3]` 形式的"
        "证据角标占位 (后续阶段会回填真证据)。直接输出 markdown, 不要前置说明。"
    )
    user_prompt = (
        f"文档类型: {type_label}\n"
        f"时间范围: {time_window}\n"
        f"当前章节标题: {title}\n\n"
        "请生成本章节的 markdown 草稿 (200-400 字, 含 2-3 个 [N] 引用占位)."
    )

    router = await get_router()
    try:
        response = await router.generate(
            task=asset_type,
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            options=LLMOptions(
                temperature=0.5,
                max_tokens=800,
                timeout_seconds=90,
            ),
            project_id=project_id,
            provider_override=provider,
            model_override=model,
        )
        content = response.text.strip()
        if len(content) < 30:
            raise ValueError(f"LLM 返回内容过短: {content!r}")
        return {
            "content": content,
            "usage": response.usage,
            "fallback_used": response.fallback_used,
            "latency_ms": response.latency_ms,
        }
    except Exception as exc:
        logger.warning(
            "chapter_llm_failed_fallback",
            title=title,
            error=str(exc),
        )
        return {
            "content": _placeholder_content(title, asset_type),
            "usage": {},
            "fallback_used": True,
            "latency_ms": 0,
        }


# T07 Mock Event 模板: 真后端会查 fixture events / DB 真 events.
# 这些 EventPreview 嵌入 Evidence 让前端一次性拿到展示数据.
_MOCK_EVENT_TEMPLATES: list[dict] = [
    {
        "event_id": "evt-pr-127",
        "title": "PR #127 · 加入 EgressGate 中间件",
        "source_type": "github",
        "source_ref": "TokenKnows/api",
        "author_name": "Alice",
        "author_email": "alice@tokenknows.local",
        "content_excerpt": "合并到 main, 含 12 个 commit, +824 / -36. 实例级出域开关在中间件强制校验.",
        "external_url": "https://github.com/TokenKnows/api/pull/127",
        "citation_text": "PR #127 · @alice 合并于 2026-05-21",
        "trust_score": 0.95,
    },
    {
        "event_id": "evt-conv-001",
        "title": "讨论价值识别的 trust_score 加权公式",
        "source_type": "claude_code",
        "source_ref": "install-john-mac",
        "author_name": "示例用户",
        "author_email": "demo@tokenknows.local",
        "content_excerpt": "trust_score = 0.3*source_authority + 0.2*corroboration + 0.2*recency + 0.3*extraction_confidence. manual_trust_override 永远覆盖.",
        "external_url": None,
        "citation_text": "Claude Code 对话 · 2026-05-21 16:30",
        "trust_score": 0.82,
    },
    {
        "event_id": "evt-issue-89",
        "title": "Issue #89 · pgvector 在 1M 行性能 spike",
        "source_type": "github",
        "source_ref": "TokenKnows/api",
        "author_name": "Alice",
        "author_email": "alice@tokenknows.local",
        "content_excerpt": "1M 行 events 表上 ivfflat lists=100 查询 p95 ~ 280ms, 超出 SLA. 建议切 HNSW 或 lists=1000.",
        "external_url": "https://github.com/TokenKnows/api/issues/89",
        "citation_text": "Issue #89 · @alice 创建于 2026-05-21",
        "trust_score": 0.75,
    },
    {
        "event_id": "evt-commit-a7f3",
        "title": "feat(llm): 实例级出域开关在中间件强制校验",
        "source_type": "github",
        "source_ref": "TokenKnows/api",
        "author_name": "Alice",
        "author_email": "alice@tokenknows.local",
        "content_excerpt": "新增 LLMRouter._egress_check 检查 instance ∧ project ∧ task 三层; 任一 OFF 抛 EgressDeniedError.",
        "external_url": "https://github.com/TokenKnows/api/commit/a7f3e91",
        "citation_text": "commit a7f3e91 · @alice 提交",
        "trust_score": 0.7,
    },
    {
        "event_id": "evt-conv-rca",
        "title": "排查 worker-extract 内存泄漏",
        "source_type": "claude_code",
        "source_ref": "install-bob-linux",
        "author_name": "Bob",
        "author_email": "bob@tokenknows.local",
        "content_excerpt": "PyTorch tensor 未 detach 累积在 CUDA cache. 修: torch.cuda.empty_cache() + with torch.no_grad().",
        "external_url": None,
        "citation_text": "Claude Code 对话 · @bob · 2026-05-21",
        "trust_score": 0.88,
    },
]


async def _stage_evidence(asset_id: str, req: GenerateAssetRequest) -> dict:
    """阶段 4 · 证据链回填 (★ 用真 events).

    选择策略 (MVP):
        - 拉 project 最近 30 天 events (limit 300)
        - 跨 source_type 多样性: 优先每章混入 claude_code / github / cursor 各一
        - 同 chapter 按 occurred_at desc 取 3-4 条
        - 同 event_id 不重复 (一章里)

    生产可换: chapter title embedding × event content embedding cosine
    """
    import random

    asset = _assets[asset_id]
    db = get_db()
    week_ago_30 = (
        _now() - timedelta(days=30)
    ).isoformat()

    # 一次拉够, in-memory 切片
    all_events, _ = db.list_events(
        project_id=asset.project_id,
        from_iso=week_ago_30,
        limit=300,
    )
    if not all_events:
        # fallback: 没真 events → 跳过 (老 demo asset 仍可看)
        logger.warning(
            "evidence_stage_no_events", asset_id=asset_id, project_id=asset.project_id
        )
        return {
            "evidence_total": 0,
            "evidence_stale": 0,
            "fallback_used": True,
            "chapters_with_evidence": 0,
            "reason": "no events in project, run plugins first",
        }

    # 按 source_type 分桶, 用于跨源采样
    by_source: dict[str, list[dict]] = {}
    for e in all_events:
        by_source.setdefault(e.get("source_type", "other"), []).append(e)

    chapters = _chapters.get(asset_id, [])
    total_evidence = 0
    for ch in chapters:
        # 每章 3-4 条, 跨源轮询
        num = random.randint(3, 4)
        chosen: list[dict] = _pick_diverse_events(by_source, num)
        ev_list: list[Evidence] = []
        content_len = max(50, len(ch.content))
        for idx, ev_raw in enumerate(chosen):
            span_start = random.randint(0, max(1, content_len - 50))
            span_end = min(content_len, span_start + random.randint(20, 50))
            ev_list.append(_build_evidence_from_event(ev_raw, ch.id, idx, span_start, span_end))
        _evidence_by_chapter[ch.id] = ev_list
        total_evidence += len(ev_list)

    logger.info(
        "evidence_linked_real",
        asset_id=asset_id,
        events_in_window=len(all_events),
        sources=list(by_source.keys()),
        total_evidence=total_evidence,
    )
    return {
        "evidence_total": total_evidence,
        "evidence_stale": 0,
        "fallback_used": False,
        "chapters_with_evidence": len(chapters),
        "real_event_pool_size": len(all_events),
    }


def _pick_diverse_events(by_source: dict[str, list[dict]], num: int) -> list[dict]:
    """跨 source 轮询, 同源内按 occurred_at desc."""
    import random
    sources = list(by_source.keys())
    random.shuffle(sources)
    out: list[dict] = []
    seen_ids: set[str] = set()
    while len(out) < num and sources:
        for s in sources[:]:
            bucket = by_source[s]
            # 取最新的一条且未用过的
            picked = None
            for e in bucket:
                if e["id"] not in seen_ids:
                    picked = e
                    break
            if picked is not None:
                out.append(picked)
                seen_ids.add(picked["id"])
                bucket.remove(picked)
            else:
                sources.remove(s)
            if len(out) >= num:
                break
    return out


def _build_evidence_from_event(
    event: dict,
    chapter_id: str,
    idx: int,
    span_start: int,
    span_end: int,
) -> Evidence:
    """从真 events 表的 row dict 构 Evidence."""
    import random
    eid = event["id"]
    author = event.get("author") or {}
    content = event.get("content") or ""
    # 在 payload 里找外链
    payload = event.get("payload") or {}
    external_url = (
        payload.get("html_url")
        or payload.get("external_url")
        or payload.get("url")
    )
    # 优先 event 自己的 trust_score, 没有给个合理范围
    trust_score = event.get("trust_score")
    if trust_score is None:
        # 基于 source_type 给个默认: github 0.85 / claude_code 0.75 / cursor 0.7 / 其它 0.6
        st = event.get("source_type", "")
        trust_score = {"github": 0.85, "claude_code": 0.75, "cursor": 0.70}.get(st, 0.60)
    citation_strength = round(trust_score * (0.85 + random.random() * 0.15), 3)

    # citation_text: e.g. "PR #127 由 @alice 合并于 2026-05-21"
    src_type = event.get("source_type", "?")
    citation_text = f"{src_type} · {author.get('name','?')} · {(event.get('occurred_at') or '')[:10]}"

    return Evidence(
        id=f"ev-{chapter_id}-{idx + 1}",
        chapter_id=chapter_id,
        event_id=eid,
        event_version=event.get("version", 1),
        span_start=span_start,
        span_end=span_end,
        citation_text=citation_text,
        manually_added=False,
        stale=False,
        trust_score=trust_score,
        citation_strength=citation_strength,
        event_preview=EvidencePreview(
            event_id=eid,
            title=event.get("title") or (content[:60] if content else "(无标题)"),
            source_type=src_type,
            source_ref=event.get("source_ref") or "",
            author_name=author.get("name"),
            author_email=author.get("email"),
            occurred_at=event.get("occurred_at") or "",
            content_excerpt=(content[:240] + "…") if len(content) > 240 else content,
            external_url=external_url,
        ),
    )


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
        _persist_asset(asset_id)   # P1 持久化

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
        _persist_asset(asset_id)   # P1: pipeline 完成态
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
        # _run_stage 已经写入失败状态 + 已 _persist_asset


# ─── 查询 API ─────────────────────────────────────────────────────


def get_asset(asset_id: str) -> Asset | None:
    return _assets.get(asset_id)


def list_chapters(asset_id: str) -> list[Chapter]:
    return _chapters.get(asset_id, [])


def list_chapter_evidence(asset_id: str, chapter_id: str) -> list[Evidence]:
    """T07 抽屉打开时一次性加载本章所有 Evidence."""
    return _evidence_by_chapter.get(chapter_id, [])


# ─── T08 · 章节重生成 ────────────────────────────────────────────


async def regenerate_chapter(
    asset_id: str,
    chapter_id: str,
    instruction: str,
    user_id: str | None = None,
    model_override: str | None = None,
    provider_override: str | None = None,
) -> Chapter | None:
    """T08 · 用用户指令重生成单章节内容.

    流程:
      1. 找到 chapter
      2. router.generate(task=asset.type, ...) 注入 instruction
      3. 更新 chapter.content + generated_by + regeneration_history
      4. 失败 → 抛, 不动 chapter
      5. 推 SSE chapter_completed 让前端订阅者同步

    返回更新后的 Chapter, 找不到返回 None.
    """
    chapters = _chapters.get(asset_id, [])
    chapter = next((c for c in chapters if c.id == chapter_id), None)
    if chapter is None:
        return None

    asset = _assets.get(asset_id)
    if asset is None:
        return None

    settings = get_settings()
    provider = provider_override or settings.task_provider(asset.type)
    model = model_override or settings.task_model(asset.type)
    type_label = {
        "weekly_report": "项目周报",
        "tech_design": "技术方案",
        "adr": "ADR 架构决策记录",
        "incident": "问题复盘报告",
    }[asset.type]

    system_prompt = (
        "你是 AI 研发知识资产平台的章节重写助手。根据用户指令重写指定章节,"
        "保留 markdown 格式与 [N] 证据角标占位风格 (后续阶段回填). 直接输出"
        "新的 markdown 内容, 不要解释、不要前置说明。"
    )
    user_prompt = (
        f"文档类型: {type_label}\n"
        f"章节标题: {chapter.title}\n\n"
        f"现有章节内容 (作为参考, 不必照搬):\n```markdown\n{chapter.content}\n```\n\n"
        f"用户重生成指令:\n{instruction}\n\n"
        "请按指令产出本章节的新版本 markdown (200-500 字)."
    )

    router = await get_router()
    response = await router.generate(
        task=asset.type,
        messages=[
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ],
        options=LLMOptions(
            temperature=0.6,
            max_tokens=900,
            timeout_seconds=90,
        ),
        project_id=asset.project_id,
        user_id=user_id,
        provider_override=provider,
        model_override=model,
    )
    new_content = response.text.strip()
    if len(new_content) < 30:
        raise ValueError(f"LLM 返回内容过短: {new_content!r}")

    # P3 · diff 准备: 把旧内容快照存进 history (前端 T12 diff 视图用)
    previous_content = chapter.content
    chapter.regeneration_history.append(
        {
            "at": _now().isoformat(),
            "user_id": user_id or "anonymous",
            "instruction": instruction,
            "model": f"{provider}/{model}",
            "previous_content": previous_content,    # P3 快照
        }
    )

    chapter.content = new_content
    chapter.generated_by = ChapterGeneratedBy(
        model=model,
        provider=provider,
        latency_ms=response.latency_ms,
        prompt_tokens=response.usage.get("prompt_tokens", 0),
        completion_tokens=response.usage.get("completion_tokens", 0),
    )
    asset.updated_at = _now()
    _persist_asset(asset_id)   # P1

    # 推 SSE 通知其它订阅者 (例如同步的协作端).
    # 复用 stage="content" - regenerate 是 content 阶段的局部重跑.
    await _publish_event(
        asset_id,
        SseEvent(
            event="chapter_completed",
            asset_id=asset_id,
            stage="content",
            payload={
                "chapter_id": chapter_id,
                "order_index": chapter.order_index,
                "regenerated": True,
                "provider": response.provider,
                "model": response.model_used,
                "fallback_used": response.fallback_used,
            },
            ts=_now(),
        ),
    )
    logger.info(
        "chapter_regenerated",
        asset_id=asset_id,
        chapter_id=chapter_id,
        provider=response.provider,
        model=response.model_used,
        fallback_used=response.fallback_used,
        tokens=response.usage,
    )
    return chapter



def get_progress(asset_id: str) -> GenerationProgress | None:
    return _progress.get(asset_id)


def list_assets(project_id: str) -> list[Asset]:
    return [a for a in _assets.values() if a.project_id == project_id]


def delete_asset(asset_id: str) -> bool:
    """硬删 (内存 + SQLite CASCADE)."""
    if asset_id not in _assets:
        return False
    _assets.pop(asset_id, None)
    _chapters.pop(asset_id, None)
    _progress.pop(asset_id, None)
    _sse_queues.pop(asset_id, None)
    _redaction_jobs.pop(asset_id, None)
    # P1: SQLite 删 (FK CASCADE 自动级联 chapters/evidence/progress/redaction/publish)
    get_db().delete_asset(asset_id)
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
    _persist_asset(new_id)   # P1
    return cloned


def update_chapter_content(
    asset_id: str, chapter_id: str, content: str
) -> Chapter | None:
    """更新章节内容 (T06 Phase 2 自动保存).

    服务端可能改 content (后续脱敏/格式化), 返回 server-side 结果让前端 reconcile.
    """
    chapters = _chapters.get(asset_id)
    if not chapters:
        return None
    for c in chapters:
        if c.id == chapter_id:
            c.content = content
            # 更新 asset.updated_at
            asset = _assets.get(asset_id)
            if asset is not None:
                asset.updated_at = _now()
            _persist_asset(asset_id)   # P1
            return c
    return None


# ─── T09 · 审批 (chapter 级 + asset 级) ────────────────────────


def approve_chapter(asset_id: str, chapter_id: str) -> Chapter | None:
    """T09 · 章节级通过. 全部通过时把 asset.approval_state 升 approved + status review→approved."""
    chapter = _find_chapter(asset_id, chapter_id)
    if chapter is None:
        return None
    chapter.approval_state = "approved"
    _refresh_asset_approval(asset_id)
    _persist_asset(asset_id)   # P1
    return chapter


def reject_chapter(asset_id: str, chapter_id: str, reason: str) -> Chapter | None:
    """T09 · 章节级退回. 任一章节退回时 asset.approval_state = 'rejected'."""
    chapter = _find_chapter(asset_id, chapter_id)
    if chapter is None:
        return None
    chapter.approval_state = "rejected"
    # 记录退回理由到 regeneration_history (复用现成字段, 不新建)
    chapter.regeneration_history.append(
        {
            "at": _now().isoformat(),
            "user_id": "reviewer",
            "instruction": f"[REJECT] {reason}",
            "model": "human",
        }
    )
    asset = _assets.get(asset_id)
    if asset is not None:
        asset.approval_state = "rejected"
        asset.updated_at = _now()
    _persist_asset(asset_id)   # P1
    return chapter


def submit_asset_for_review(asset_id: str) -> Asset | None:
    """T09 · 文档作者提交审批: status draft → in_review."""
    asset = _assets.get(asset_id)
    if asset is None:
        return None
    asset.status = "in_review"
    asset.updated_at = _now()
    # 同时把所有 chapter 的 approval_state 重置为 pending (上一轮 reject 状态清掉)
    chapters = _chapters.get(asset_id, [])
    for c in chapters:
        c.approval_state = "pending"
    asset.approval_state = "pending"
    _persist_asset(asset_id)   # P1
    return asset


def _find_chapter(asset_id: str, chapter_id: str) -> Chapter | None:
    chapters = _chapters.get(asset_id, [])
    return next((c for c in chapters if c.id == chapter_id), None)


# ─── T11/T12 · 发布 ──────────────────────────────────────────


def publish_asset(
    asset_id: str,
    destinations: list[str],
    publish_mode: str,
    visibility: str | None = None,
    user_id: str | None = None,
) -> list[PublishRecord]:
    """T11 · 创建多渠道发布记录. 每个 destination 一条 record.

    MVP: 不实际渲染 PDF/DOCX, 也不实际推到 Slack/Feishu, 只生成记录 + URL.
    """
    asset = _assets.get(asset_id)
    if asset is None:
        raise ValueError("Asset not found")

    if not destinations:
        raise ValueError("至少选择一个发布渠道")

    valid_destinations = {"internal", "public_link", "export_md"}
    if any(d not in valid_destinations for d in destinations):
        raise ValueError(f"未知 destination, 允许: {sorted(valid_destinations)}")

    if publish_mode not in {"full", "summary_with_backlink"}:
        raise ValueError("publish_mode 必须是 full 或 summary_with_backlink")

    records: list[PublishRecord] = []
    for dest in destinations:
        rec_id = f"pub-{uuid4().hex[:10]}"
        # 计算 URL
        token = uuid4().hex[:16]
        if dest == "internal":
            url: str | None = f"/internal/assets/{asset_id}/v{asset.current_version}"
            dest_ref: str | None = url
        elif dest == "public_link":
            url = f"https://share.tokenknows.dev/p/{token}"
            dest_ref = token
        elif dest == "export_md":
            url = f"/api/v1/publish-records/{rec_id}/download"
            dest_ref = f"asset-{asset_id}-v{asset.current_version}.md"
        else:
            url = None
            dest_ref = None

        record = PublishRecord(
            id=rec_id,
            asset_id=asset_id,
            asset_version=asset.current_version or 1,
            destination=dest,
            destination_ref=dest_ref,
            publish_mode=publish_mode,
            status="success",
            url=url,
            published_at=_now().isoformat(),
            published_by=user_id or "anonymous",
            visibility=visibility if dest == "public_link" else None,
        )
        _publish_records[rec_id] = record
        records.append(record)
        _persist_publish_record(rec_id)   # P1

    # 推进 asset 状态 → published
    asset.status = "published"
    asset.updated_at = _now()
    _persist_asset(asset_id)   # P1

    logger.info(
        "asset_published",
        asset_id=asset_id,
        destinations=destinations,
        records=[r.id for r in records],
    )
    return records


def get_publish_record(record_id: str) -> PublishRecord | None:
    return _publish_records.get(record_id)


def list_publish_records_for_asset(asset_id: str) -> list[PublishRecord]:
    return [r for r in _publish_records.values() if r.asset_id == asset_id]


# ─── T10 · 脱敏扫描 (同步, 正则) ─────────────────────────────


# 内置正则规则 (MVP demo; 生产由 T13 项目设置 + LLM 兜底)
_REDACTION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "EMAIL",
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}"),
        "[EMAIL]",
    ),
    (
        "API_KEY",
        # OpenAI sk-proj-/sk-, Anthropic sk-ant-, GitHub ghp_, Stripe sk_live_
        re.compile(r"(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|sk_live_[A-Za-z0-9]{16,})"),
        "[API_KEY]",
    ),
    (
        "IP",
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "[IP]",
    ),
    (
        "INTERNAL",
        # 内部代号示例: 项目缩写_环境 / inc-XXX / 客户名 (MVP 硬编码, 生产由 T13 自定义)
        re.compile(r"\b(?:Project[_-][A-Z][A-Za-z0-9_-]*|inc-\d{2,}|customer-[A-Z][A-Za-z0-9_-]*)\b"),
        "[INTERNAL]",
    ),
]


def scan_redaction(asset_id: str) -> RedactionScanJob | None:
    """T10 · 同步扫所有章节内容找敏感内容. 生产: 异步 + Celery + LLM 兜底."""
    chapters = _chapters.get(asset_id, [])
    if not chapters:
        return None

    items: list[RedactionItem] = []
    seen: set[tuple[str, str]] = set()  # (type, matched_text) 去重
    for ch in chapters:
        for type_name, pattern, replacement in _REDACTION_PATTERNS:
            for m in pattern.finditer(ch.content):
                text = m.group(0)
                key = (type_name, text)
                if key in seen:
                    continue
                seen.add(key)
                ctx_before = ch.content[max(0, m.start() - 30): m.start()]
                ctx_after = ch.content[m.end(): m.end() + 30]
                items.append(
                    RedactionItem(
                        id=f"red-{uuid4().hex[:8]}",
                        chapter_id=ch.id,
                        span_start=m.start(),
                        span_end=m.end(),
                        type=type_name,
                        matched_text=text,
                        rule_source="rule",
                        suggested_replacement=replacement,
                        status="pending",
                        context_before=ctx_before,
                        context_after=ctx_after,
                    )
                )

    job = RedactionScanJob(
        job_id=f"redjob-{uuid4().hex[:8]}",
        asset_id=asset_id,
        status="done",
        progress=1.0,
        items=items,
    )
    _redaction_jobs[asset_id] = job

    # 同时把 asset.redaction_state 变更为 'any_unresolved' (有命中) / 'all_confirmed' (无命中)
    asset = _assets.get(asset_id)
    if asset is not None:
        asset.redaction_state = "all_confirmed" if not items else "any_unresolved"
        asset.updated_at = _now()
    _persist_redaction_job(asset_id)   # P1
    _persist_asset(asset_id)
    return job


def get_redaction_job(asset_id: str) -> RedactionScanJob | None:
    return _redaction_jobs.get(asset_id)


def confirm_redaction(asset_id: str, item_ids: list[str]) -> RedactionScanJob | None:
    job = _redaction_jobs.get(asset_id)
    if job is None:
        return None
    id_set = set(item_ids)
    for item in job.items:
        if item.id in id_set and item.status == "pending":
            item.status = "confirmed"
    _refresh_redaction_state(asset_id, job)
    _persist_redaction_job(asset_id)   # P1
    _persist_asset(asset_id)
    return job


def exempt_redaction(asset_id: str, item_id: str, reason: str) -> RedactionScanJob | None:
    job = _redaction_jobs.get(asset_id)
    if job is None:
        return None
    for item in job.items:
        if item.id == item_id and item.status == "pending":
            item.status = "exempted"
            item.reason = reason.strip()
            break
    _refresh_redaction_state(asset_id, job)
    _persist_redaction_job(asset_id)   # P1
    _persist_asset(asset_id)
    return job


def _refresh_redaction_state(asset_id: str, job: RedactionScanJob) -> None:
    """所有 item 都 not pending → asset.redaction_state='all_confirmed'."""
    asset = _assets.get(asset_id)
    if asset is None:
        return
    if all(it.status != "pending" for it in job.items):
        asset.redaction_state = "all_confirmed"
    else:
        asset.redaction_state = "any_unresolved"
    asset.updated_at = _now()


def _refresh_asset_approval(asset_id: str) -> None:
    """章节状态变化后, 重算 asset.approval_state.

    规则:
      - 任一章节 'rejected' → asset.approval_state = 'rejected'
      - 全部 'approved' → asset.approval_state = 'approved' + status 升 'approved'
      - 否则 → 'pending'
    """
    asset = _assets.get(asset_id)
    chapters = _chapters.get(asset_id, [])
    if asset is None or not chapters:
        return

    if any(c.approval_state == "rejected" for c in chapters):
        asset.approval_state = "rejected"
    elif all(c.approval_state == "approved" for c in chapters):
        asset.approval_state = "approved"
        asset.status = "approved"
    else:
        asset.approval_state = "pending"
    asset.updated_at = _now()
