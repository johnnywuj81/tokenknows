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
from app.prompts import PromptTemplate
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
    # v0.2 升级
    "book": "技术手册 · 范围 = {window}",
    "agent_skill": "Skill 草稿 · {window}",
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
    # v0.2 升级 · book 顶层卷大纲 (默认 3 卷, LLM 在 _stage_outline 里展开成完整章)
    "book": ["卷一 · 概述", "卷二 · 实现", "卷三 · 实践"],
    # v0.2 升级 · agent_skill 5 段 (SKILL.md 内容骨架)
    "agent_skill": [
        "适用场景",
        "核心原则",
        "关键步骤",
        "好例子 / 坏例子",
        "相关 skill",
    ],
    # v1.2 升级 · knowledge_graph 单 Chapter 承载图; outline 实际产 nodes 而非 titles,
    # 这里 fallback 仅一个 "图谱" 标题占位 (chapter.content 写节点 ID 索引)
    "knowledge_graph": ["实体关系图谱"],
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

    v0.2 · type=book 走两步路径: 先生成 3-5 卷, 再并行生成每卷的章.
    v1.2 · type=knowledge_graph 走实体抽取路径 (chapter.layout 承载图 JSON).
    """
    if req.type == "book":
        return await _stage_outline_book(asset_id, req)
    if req.type == "knowledge_graph":
        return await _stage_outline_knowledge_graph(asset_id, req)

    asset = _assets[asset_id]
    type_label = {
        "weekly_report": "项目周报",
        "tech_design": "技术方案",
        "adr": "ADR 架构决策记录",
        "incident": "问题复盘报告",
        "book": "技术书籍",
        "agent_skill": "Agent 专家技能",
        "knowledge_graph": "知识图谱",  # 实际不会走到此路径, 但保留 dict 完整
    }[req.type]
    fallback = _OUTLINE_TEMPLATES[req.type]

    # A1.2: 抽 prompt 到 app/prompts/outline/_default.md (4 类共享模板).
    # 字节级回归测试见 tests/test_prompts_byte_parity.py
    tpl = PromptTemplate.load("outline/_default")
    rendered = tpl.render({
        "type_label": type_label,
        "time_window": req.time_window,
        "fallback_joined": " / ".join(fallback),
    })

    router = await get_router()
    try:
        response = await router.generate(
            task=req.type,
            messages=[
                LLMMessage(role="system", content=rendered.system),
                LLMMessage(role="user", content=rendered.user),
            ],
            options=LLMOptions(**rendered.options),
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


async def _stage_outline_book(asset_id: str, req: GenerateAssetRequest) -> dict:
    """v0.2 · book 两步大纲:
        Step 1: 1 次 LLM → 3-5 卷 (含 title + description)
        Step 2: N 次 LLM 并行 → 每卷 5-10 章

    返回:
        chapter_specs: [{title, depth, parent_volume_index|None}, ...]
        flat_titles: 兼容字段 (旧前端读 titles, 看到的是 "卷一 · 概述" + "  第一章 · ..."
                              带 2 空格缩进)
        volumes: [{title, description}, ...]
        chapters_total: len(chapter_specs)
    """
    asset = _assets[asset_id]
    router = await get_router()

    fallback_specs = _book_fallback_specs()

    # ── Step 1: 卷大纲 ────────────────────────────────────────────
    vol_tpl = PromptTemplate.load("outline/book_volume")
    vol_rendered = vol_tpl.render({
        "title": asset.title,
        "time_window": req.time_window,
    })
    try:
        vol_resp = await router.generate(
            task="book",
            messages=[
                LLMMessage(role="system", content=vol_rendered.system),
                LLMMessage(role="user", content=vol_rendered.user),
            ],
            options=LLMOptions(**vol_rendered.options),
            project_id=asset.project_id,
        )
        vol_parsed = json.loads(vol_resp.text)
        volumes = vol_parsed.get("volumes") or []
        if not isinstance(volumes, list) or len(volumes) < 2:
            raise ValueError(f"LLM 卷大纲不合理: {volumes!r}")
    except Exception as exc:
        logger.warning("book_outline_volume_failed_fallback",
                       asset_id=asset_id, error=str(exc))
        return {
            "chapters_total": len(fallback_specs),
            "titles": [s["title"] for s in fallback_specs],
            "chapter_specs": fallback_specs,
            "volumes": [{"title": s["title"], "description": ""}
                        for s in fallback_specs if s["depth"] == 0],
            "llm_fallback_to_template": True,
            "llm_error": str(exc),
        }

    await _publish_event(asset_id, SseEvent(
        event="volume_outline_completed",
        asset_id=asset_id,
        stage="outline",
        payload={"volumes_total": len(volumes)},
        ts=_now(),
    ))

    # ── Step 2: 每卷章大纲 (并行) ────────────────────────────────
    ch_tpl = PromptTemplate.load("outline/book_chapters")

    async def gen_volume_chapters(vol_idx: int, vol: dict) -> tuple[int, dict, list[str]]:
        ch_rendered = ch_tpl.render({
            "book_title": asset.title,
            "volume_title": vol.get("title", f"卷{vol_idx + 1}"),
            "volume_description": vol.get("description", ""),
        })
        try:
            ch_resp = await router.generate(
                task="book",
                messages=[
                    LLMMessage(role="system", content=ch_rendered.system),
                    LLMMessage(role="user", content=ch_rendered.user),
                ],
                options=LLMOptions(**ch_rendered.options),
                project_id=asset.project_id,
            )
            ch_parsed = json.loads(ch_resp.text)
            chapters = ch_parsed.get("chapters") or []
            if not isinstance(chapters, list) or len(chapters) < 3:
                raise ValueError(f"卷 {vol_idx+1} 章大纲不合理: {chapters!r}")
        except Exception as exc:
            logger.warning("book_outline_chapters_failed_fallback",
                           asset_id=asset_id, vol=vol_idx, error=str(exc))
            chapters = [f"第{i+1}章 · 待补充内容" for i in range(5)]

        await _publish_event(asset_id, SseEvent(
            event="chapter_outline_completed",
            asset_id=asset_id,
            stage="outline",
            payload={
                "volume_index": vol_idx,
                "volume_title": vol.get("title"),
                "chapter_count": len(chapters),
            },
            ts=_now(),
        ))
        return vol_idx, vol, chapters

    vol_results = await asyncio.gather(
        *(gen_volume_chapters(i, v) for i, v in enumerate(volumes))
    )
    vol_results.sort(key=lambda x: x[0])

    # 拼装 chapter_specs: 卷 (depth=0) 在前, 紧跟其下章 (depth=1, parent_volume_index=vol_idx)
    chapter_specs: list[dict] = []
    volume_summary: list[dict] = []
    for vol_idx, vol, chapter_titles in vol_results:
        chapter_specs.append({
            "title": vol.get("title", f"卷{vol_idx + 1}"),
            "depth": 0,
            "parent_volume_index": None,
        })
        volume_summary.append({
            "title": vol.get("title"),
            "description": vol.get("description", ""),
        })
        for c in chapter_titles:
            chapter_specs.append({
                "title": c,
                "depth": 1,
                "parent_volume_index": vol_idx,
            })

    flat_titles = [
        s["title"] if s["depth"] == 0 else f"  {s['title']}"
        for s in chapter_specs
    ]

    logger.info(
        "book_outline_done",
        asset_id=asset_id,
        volumes=len(volumes),
        chapters_total=len(chapter_specs),
    )
    return {
        "chapters_total": len(chapter_specs),
        "titles": flat_titles,
        "chapter_specs": chapter_specs,
        "volumes": volume_summary,
        "provider_used": vol_resp.provider,
        "model_used": vol_resp.model_used,
        "fallback_used": False,
    }


def _book_fallback_specs() -> list[dict]:
    """卷大纲 LLM 全挂时的兜底骨架."""
    return [
        {"title": "卷一 · 概述", "depth": 0, "parent_volume_index": None},
        {"title": "第一章 · 背景", "depth": 1, "parent_volume_index": 0},
        {"title": "第二章 · 关键概念", "depth": 1, "parent_volume_index": 0},
        {"title": "卷二 · 实现", "depth": 0, "parent_volume_index": None},
        {"title": "第一章 · 架构", "depth": 1, "parent_volume_index": 1},
        {"title": "第二章 · 关键模块", "depth": 1, "parent_volume_index": 1},
        {"title": "卷三 · 实践", "depth": 0, "parent_volume_index": None},
        {"title": "第一章 · 典型场景", "depth": 1, "parent_volume_index": 2},
        {"title": "第二章 · 经验教训", "depth": 1, "parent_volume_index": 2},
    ]


async def _stage_content(asset_id: str, req: GenerateAssetRequest) -> dict:
    """阶段 3 · 章节正文生成 (per-chapter LLM call · ★ 真 LLM).

    v0.2 新增:
    - 每章生成前先 select_skills_for_chapter(top-3 active skill) 注入 system_prompt
    - chapter.applied_skills 追踪本次注入的 skill_id + version
    - record_skill_application 累加 skill.usage_count
    - type=book 走 sequential + rolling summary 路径 (_stage_content_book)

    每章一次 router.generate(task=req.type, ...) 并行执行 (asyncio.gather).
    失败的章节回退到 _placeholder_content 保证 demo 不挂.

    titles 优先从 outline 阶段产出读 (LLM 真生成的标题), 没有则 fallback 模板.
    v1.2 · type=knowledge_graph 走边关系抽取 + 节点 summary 路径.
    """
    if req.type == "book":
        return await _stage_content_book(asset_id, req)
    if req.type == "knowledge_graph":
        return await _stage_content_knowledge_graph(asset_id, req)

    from app.services import skill_service  # avoid circular import at module load

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

    # v0.2 · 每章并行召回 skill (避免阻塞主 LLM 调用)
    async def select_one(title: str) -> list:
        try:
            return await skill_service.select_skills_for_chapter(
                project_id=asset.project_id,
                query_text=f"{title}\n{req.time_window}",
            )
        except Exception as e:
            logger.warning("skill_select_failed", title=title, error=str(e))
            return []

    skill_picks_per_chapter = await asyncio.gather(
        *(select_one(t) for t in outline)
    )

    # 并行调 LLM 生章节
    async def gen_one(
        idx: int, title: str, picked: list
    ) -> tuple[int, str, str, dict, bool, int, list]:
        skill_suffix = skill_service.render_skills_for_prompt(picked)
        result = await _call_chapter_llm(
            asset.type, title, req.time_window, asset.project_id,
            provider, model, skill_suffix=skill_suffix,
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
        return (
            idx, title, result["content"], result["usage"],
            result["fallback_used"], result["latency_ms"], picked,
        )

    results = await asyncio.gather(
        *(gen_one(i, t, picks) for i, (t, picks)
          in enumerate(zip(outline, skill_picks_per_chapter)))
    )
    results.sort(key=lambda x: x[0])

    chapters: list[Chapter] = []
    total_skill_applications = 0
    for idx, title, content, usage, fb_used, latency, picked in results:
        chapter_id = f"chapter-{uuid4().hex[:8]}"
        # 写 skill 应用记录 (chapter.applied_skills + skill.usage_count +1)
        applied_records: list = []
        if picked:
            recs = skill_service.record_skill_application(
                chapter_id=chapter_id, project_id=asset.project_id, picked=picked,
            )
            applied_records = [r.model_dump(mode="json") for r in recs]
            total_skill_applications += len(applied_records)
        chapters.append(
            Chapter(
                id=chapter_id,
                asset_id=asset_id,
                asset_version=1,
                order_index=idx,
                title=title,
                content=content,
                applied_skills=applied_records,
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
        "skill_applications_count": total_skill_applications,
    }


async def _call_chapter_llm(
    asset_type: AssetType,
    title: str,
    time_window: str,
    project_id: str,
    provider: str,
    model: str,
    skill_suffix: str = "",
) -> dict[str, Any]:
    """单章节 LLM 调用 · 失败回退到 placeholder content.

    Args:
        skill_suffix: v0.2 注入的项目专家技能段 (render_skills_for_prompt 输出);
                      为空字符串时不修改 system_prompt.

    返回 {content, usage, fallback_used, latency_ms}.
    """
    type_label = {
        "weekly_report": "项目周报",
        "tech_design": "技术方案",
        "adr": "ADR 架构决策记录",
        "incident": "问题复盘报告",
        "book": "技术书籍",
        "agent_skill": "Agent 专家技能",
    }[asset_type]

    # A1.2: 抽 prompt 到 app/prompts/content/_default.md.
    tpl = PromptTemplate.load("content/_default")
    rendered = tpl.render({
        "type_label": type_label,
        "time_window": time_window,
        "title": title,
    })

    # v0.2 · skill 注入 system_prompt 末尾
    system_prompt = rendered.system
    if skill_suffix:
        system_prompt = f"{system_prompt}\n\n{skill_suffix}"

    router = await get_router()
    try:
        response = await router.generate(
            task=asset_type,
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=rendered.user),
            ],
            options=LLMOptions(**rendered.options),
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


# ─── v1.2 · Knowledge Graph 3 个 stage 分支 (T83) ─────────────


_KG_MAX_NODES = 30
"""outline stage 节点数上限, 超出按 trust_score 截断 (≤30 让 React Flow 流畅)."""

_KG_MAX_EVENTS_FOR_PROMPT = 25
"""塞进 LLM prompt 的最多 events (按 trust_score 降序; 控制 token)."""


async def _stage_outline_knowledge_graph(
    asset_id: str, req: GenerateAssetRequest
) -> dict:
    """v1.2 · knowledge_graph 节点骨架抽取.

    流程:
    1. 拉 top-N events (复用 collect stage 结果, 不重新查)
    2. 提取 contributors 列表 (im_user_id + name) 作为锚定 person 节点的依据
    3. LLM JSON mode → KGOutlineLLMOutput (含 nodes)
    4. 截断到 _KG_MAX_NODES (按 trust_score)
    5. 创建一个 fake "图谱" Chapter (order_index=0, content=节点 ID 索引锚点行,
       layout 暂留 nodes; edges 留 content stage 填)
    """
    from app.services.knowledge_graph.assess import dedup_nodes
    from app.schemas.knowledge_graph import (
        KGOutlineLLMOutput,
        KnowledgeGraphLayout,
    )

    asset = _assets[asset_id]
    progress = _progress[asset_id]
    settings = get_settings()
    router = await get_router()

    # 从 collect stage metadata 取 events; fallback 空
    collect_idx = _stage_index(progress, "collect")
    events: list[dict] = (
        (progress.stages[collect_idx].metadata or {}).get("events") or []
    )

    # 提 contributors (按 im_user_id 去重)
    contributors_by_uid: dict[str, dict] = {}
    for e in events:
        author = e.get("author") or {}
        uid = author.get("im_user_id") or author.get("email")
        if uid and uid not in contributors_by_uid:
            contributors_by_uid[uid] = {
                "im_user_id": uid,
                "name": author.get("name") or uid,
            }

    contributors_block = "\n".join(
        f"- im_user_id={c['im_user_id']}, name={c['name']}"
        for c in contributors_by_uid.values()
    ) or "(无 contributors, 仅生成 event/concept/artifact 节点)"

    # 截 events 到 _KG_MAX_EVENTS_FOR_PROMPT (假设已按 trust 排序)
    short_events = events[:_KG_MAX_EVENTS_FOR_PROMPT]
    events_block = "\n".join(
        f"- evt_id={e.get('id', '')}, type={e.get('type', '')}, "
        f"title={(e.get('payload', {}) or {}).get('title') or e.get('source_ref', '')[:80]}, "
        f"trust={e.get('trust_score', 0.5):.2f}"
        for e in short_events
    ) or "(无候选 events)"

    layout = KnowledgeGraphLayout()
    try:
        tpl = PromptTemplate.load("outline/knowledge_graph")
        rendered = tpl.render({
            "project_id": asset.project_id,
            "time_window": req.time_window or "近 30 天",
            "contributors_block": contributors_block,
            "events_count": len(short_events),
            "events_block": events_block,
        })
        resp = await router.generate(
            task="knowledge_graph",
            messages=[
                LLMMessage(role="system", content=rendered.system),
                LLMMessage(role="user", content=rendered.user),
            ],
            options=LLMOptions(**rendered.options),
            project_id=asset.project_id,
        )
        parsed_dict = json.loads(resp.text)
        parsed = KGOutlineLLMOutput.model_validate(parsed_dict)
        nodes = parsed.nodes

        # 截断到 _KG_MAX_NODES (按 trust_score 降序)
        if len(nodes) > _KG_MAX_NODES:
            nodes = sorted(
                nodes, key=lambda n: n.trust_score, reverse=True
            )[:_KG_MAX_NODES]

        # 部分 dedup 已可做 (assess 阶段会再跑一次完整版)
        nodes, _, _ = dedup_nodes(nodes, [])
        layout.nodes = nodes
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "kg_outline_llm_failed", asset_id=asset_id, error=str(e)
        )
        layout.parse_error = f"outline_stage: {type(e).__name__}: {e}"
        # 兜底: 仅创建 contributors 的 person 节点 (零 LLM 兜底也能跑)
        from app.schemas.knowledge_graph import KGNode
        layout.nodes = [
            KGNode(
                id=f"n_{i}",
                type="person",
                label=c["name"],
                properties={"im_user_id": c["im_user_id"]},
                trust_score=0.5,
            )
            for i, c in enumerate(contributors_by_uid.values())
        ]

    # 创建 fake "图谱" Chapter, content=节点 ID 索引 (供 EvidenceDrawer 锚点)
    content_lines: list[str] = ["# 实体关系图谱\n"]
    for node in layout.nodes:
        # span_anchor 用当前 char_offset
        char_offset = sum(len(line) + 1 for line in content_lines)
        # 在 layout.nodes 中 in-place 更新 span_anchor
        idx = next(i for i, n in enumerate(layout.nodes) if n.id == node.id)
        from app.schemas.knowledge_graph import KGSpanAnchor
        layout.nodes[idx] = node.model_copy(update={
            "span_anchor": KGSpanAnchor(char_offset=char_offset),
        })
        content_lines.append(
            f"<!-- node:{node.id} type={node.type} -->"
        )
        content_lines.append(f"- **{node.label}** [`{node.type}`]")
        content_lines.append("")

    full_content = "\n".join(content_lines)
    titles = ["实体关系图谱"]
    # 返回 outline stage 标准结构, layout 通过 metadata 透传给 content stage
    return {
        "titles": titles,
        "chapter_count": 1,
        "method": "llm" if layout.parse_error is None else "fallback_contributors_only",
        "node_count": len(layout.nodes),
        # 临时存图; content stage 会读出来 + 加 edges
        "_kg_layout": layout.model_dump(mode="json"),
        "_kg_content": full_content,
    }


async def _stage_content_knowledge_graph(
    asset_id: str, req: GenerateAssetRequest
) -> dict:
    """v1.2 · knowledge_graph 边关系抽取 + node_summaries.

    流程:
    1. 从 outline stage metadata 取 layout (nodes) + content
    2. LLM JSON mode → KGContentLLMOutput (edges + node_summaries)
    3. 校验 edge.source/target ∈ nodes; 否则丢弃
    4. merge node_summaries 回 nodes
    5. 创建单 Chapter (order_index=0, content=节点索引, layout=完整图)
    """
    from app.schemas.knowledge_graph import (
        KGContentLLMOutput,
        KnowledgeGraphLayout,
    )

    asset = _assets[asset_id]
    progress = _progress[asset_id]
    router = await get_router()

    # 从 outline metadata 取
    outline_idx = _stage_index(progress, "outline")
    outline_meta = progress.stages[outline_idx].metadata or {}
    layout_dict = outline_meta.get("_kg_layout") or {}
    content_md = outline_meta.get("_kg_content") or "# 实体关系图谱\n"
    layout = KnowledgeGraphLayout.model_validate(
        layout_dict
    ) if layout_dict else KnowledgeGraphLayout()

    # 从 collect 取 events 给 prompt
    collect_idx = _stage_index(progress, "collect")
    events: list[dict] = (
        (progress.stages[collect_idx].metadata or {}).get("events") or []
    )
    events_short = events[:_KG_MAX_EVENTS_FOR_PROMPT]
    events_block = "\n".join(
        f"- evt_id={e.get('id', '')}: {(e.get('payload', {}) or {}).get('title') or e.get('source_ref', '')[:100]}"
        for e in events_short
    ) or "(无 events)"

    nodes_block = "\n".join(
        f"- {n.id} ({n.type}): {n.label}" for n in layout.nodes
    ) or "(无 nodes)"

    edges_added = 0
    if layout.nodes:
        try:
            tpl = PromptTemplate.load("content/knowledge_graph")
            rendered = tpl.render({
                "project_id": asset.project_id,
                "nodes_count": len(layout.nodes),
                "nodes_block": nodes_block,
                "events_count": len(events_short),
                "events_block": events_block,
            })
            resp = await router.generate(
                task="knowledge_graph",
                messages=[
                    LLMMessage(role="system", content=rendered.system),
                    LLMMessage(role="user", content=rendered.user),
                ],
                options=LLMOptions(**rendered.options),
                project_id=asset.project_id,
            )
            parsed = KGContentLLMOutput.model_validate(json.loads(resp.text))

            # 过滤 edge: source / target 必须 ∈ nodes
            node_ids = {n.id for n in layout.nodes}
            valid_edges = [
                e for e in parsed.edges
                if e.source in node_ids and e.target in node_ids
            ]
            layout.edges = valid_edges
            edges_added = len(valid_edges)

            # merge node_summaries
            summary_map = {s.node_id: s.summary for s in parsed.node_summaries}
            for i, n in enumerate(layout.nodes):
                if n.id in summary_map:
                    layout.nodes[i] = n.model_copy(
                        update={"summary": summary_map[n.id]}
                    )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "kg_content_llm_failed", asset_id=asset_id, error=str(e)
            )
            layout.parse_error = (layout.parse_error or "") + (
                f" | content_stage: {type(e).__name__}: {e}"
            )

    # 创建 Chapter (单一, order_index=0, content + layout)
    chapter_id = f"ch-{asset_id}-kg"
    now_iso = _now()
    chapter = Chapter(
        id=chapter_id,
        asset_id=asset_id,
        order_index=0,
        title="实体关系图谱",
        content=content_md,
        layout=layout.model_dump(mode="json"),
        approval_state="pending",
    )
    _chapters[asset_id] = [chapter]
    return {
        "chapters_created": 1,
        "edges_added": edges_added,
        "node_count": len(layout.nodes),
        "method": "llm" if layout.parse_error is None else "fallback",
    }


async def _stage_assess_knowledge_graph(
    asset_id: str, req: GenerateAssetRequest
) -> dict:
    """v1.2 · knowledge_graph 专属 assess:
    dedup + bidirect_contradicts + isolated 告警 + AssetMetrics 计算.
    """
    from app.schemas.knowledge_graph import KnowledgeGraphLayout
    from app.services.knowledge_graph.assess import (
        bidirect_contradicts,
        compute_assess_metrics,
        dedup_nodes,
        find_isolated_nodes,
    )

    asset = _assets[asset_id]
    chapters = _chapters.get(asset_id, [])
    if not chapters:
        logger.warning("kg_assess_no_chapters", asset_id=asset_id)
        return {"error": "no_chapters"}

    chapter = chapters[0]
    layout = KnowledgeGraphLayout.model_validate(chapter.layout or {})

    # 1. dedup (assess 全量 dedup, 即便 outline 已 dedup 过, 这里多一道防线)
    new_nodes, new_edges, merged_count = dedup_nodes(
        layout.nodes, layout.edges
    )
    # 2. bidirect contradicts
    new_edges = bidirect_contradicts(new_edges)
    # 3. isolated
    isolated_ids = find_isolated_nodes(new_nodes, new_edges)
    # 4. metrics
    raw_metrics = compute_assess_metrics(
        new_nodes, new_edges, isolated_ids, merged_count
    )

    # 写回 layout
    layout.nodes = new_nodes
    layout.edges = new_edges
    chapter.layout = layout.model_dump(mode="json")

    # AssetMetrics
    asset.metrics = AssetMetrics(
        coverage=raw_metrics["coverage"],
        citation_density=raw_metrics["citation_density"],
        slop_score=raw_metrics["slop_score"],
        similarity=raw_metrics["similarity"],
        consistency_score=raw_metrics["consistency_score"],
    )
    asset.updated_at = _now()
    _persist_asset(asset_id)

    logger.info(
        "kg_assess_done",
        asset_id=asset_id,
        nodes=len(new_nodes),
        edges=len(new_edges),
        merged=merged_count,
        isolated=len(isolated_ids),
    )
    return {
        "node_count": len(new_nodes),
        "edge_count": len(new_edges),
        "merged_count": merged_count,
        "isolated_count": len(isolated_ids),
        "metrics": raw_metrics,
    }


# ─── v0.2 · Book sequential content + rolling summary ────────────


_BOOK_SUMMARY_MAX_CHARS = 1500
"""running_summary 拼接进 prompt 的最大字符数 (滚动截断, 保留最新部分)."""


async def _stage_content_book(asset_id: str, req: GenerateAssetRequest) -> dict:
    """v0.2 · book 顺序生成 + rolling summary.

    设计:
    - 卷 (depth=0): 空内容, 仅作 chapter parent 占位 (不调 LLM)
    - 章 (depth=1): 串行调 LLM (前后依赖, 不能并行), prompt 拼前文 summary
    - 每章写完后, 调 1 次轻量 LLM 摘要, 追加到 running_summary

    chapter_specs 从 outline 阶段读. 失败时回退到 _book_fallback_specs.
    """
    from app.services import skill_service

    settings = get_settings()
    progress = _progress[asset_id]
    outline_stage = next(
        (s for s in progress.stages if s.name == "outline"), None
    )
    chapter_specs = (
        outline_stage.metadata.get("chapter_specs") if outline_stage else None
    ) or _book_fallback_specs()
    asset = _assets[asset_id]
    provider = req.provider_override or settings.task_provider("book")
    model = req.model_override or settings.task_model("book")

    book_title = asset.title
    chapters: list[Chapter] = []
    volume_id_by_index: dict[int, str] = {}
    running_summary_parts: list[str] = []
    successful_chapters = 0
    fallback_count = 0
    total_skill_applications = 0

    for order_idx, spec in enumerate(chapter_specs):
        chapter_id = f"chapter-{uuid4().hex[:8]}"
        depth = spec.get("depth", 0)
        parent_vol_idx = spec.get("parent_volume_index")
        title = spec.get("title", f"章节 {order_idx + 1}")

        if depth == 0:
            # 卷: 空内容占位
            volume_id_by_index[order_idx_to_vol_idx(chapter_specs, order_idx)] = chapter_id
            chapters.append(Chapter(
                id=chapter_id,
                asset_id=asset_id,
                asset_version=1,
                order_index=order_idx,
                parent_id=None,
                depth=0,
                title=title,
                content="",
            ))
            continue

        # 章: 拼 rolling summary + 选 skill
        running_summary = _truncate_summary(running_summary_parts)
        volume_title = ""
        if parent_vol_idx is not None and 0 <= parent_vol_idx < len(chapter_specs):
            # 找到该卷的 spec (与 volume_id_by_index 索引对齐)
            vol_specs = [s for s in chapter_specs if s.get("depth") == 0]
            if parent_vol_idx < len(vol_specs):
                volume_title = vol_specs[parent_vol_idx].get("title", "")

        try:
            picked = await skill_service.select_skills_for_chapter(
                project_id=asset.project_id,
                query_text=f"{title}\n{volume_title}",
            )
        except Exception as e:
            logger.warning("book_skill_select_failed", title=title, error=str(e))
            picked = []
        skill_suffix = skill_service.render_skills_for_prompt(picked)

        result = await _call_book_chapter_llm(
            book_title=book_title,
            volume_title=volume_title,
            chapter_title=title,
            running_summary=running_summary,
            project_id=asset.project_id,
            provider=provider,
            model=model,
            skill_suffix=skill_suffix,
        )
        if result["fallback_used"]:
            fallback_count += 1
        else:
            successful_chapters += 1

        applied_records: list = []
        if picked and not result["fallback_used"]:
            recs = skill_service.record_skill_application(
                chapter_id=chapter_id, project_id=asset.project_id, picked=picked,
            )
            applied_records = [r.model_dump(mode="json") for r in recs]
            total_skill_applications += len(applied_records)

        parent_id = (
            volume_id_by_index.get(parent_vol_idx)
            if parent_vol_idx is not None else None
        )
        chapters.append(Chapter(
            id=chapter_id,
            asset_id=asset_id,
            asset_version=1,
            order_index=order_idx,
            parent_id=parent_id,
            depth=1,
            title=title,
            content=result["content"],
            applied_skills=applied_records,
            generated_by=ChapterGeneratedBy(
                model=model,
                provider=provider,
                latency_ms=result["latency_ms"],
                prompt_tokens=result["usage"].get("prompt_tokens", 0),
                completion_tokens=result["usage"].get("completion_tokens", 0),
            ),
        ))

        await _publish_event(asset_id, SseEvent(
            event="chapter_completed",
            asset_id=asset_id,
            stage="content",
            payload={"order_index": order_idx, "title": title, "total": len(chapter_specs)},
            ts=_now(),
        ))

        # rolling summary: 写完后总结, 追加 (失败用截断兜底)
        try:
            summary = await _summarize_book_chapter(
                chapter_title=title,
                chapter_content=result["content"],
                project_id=asset.project_id,
            )
        except Exception as e:
            logger.warning("book_summary_failed", title=title, error=str(e))
            summary = result["content"][:160]
        if summary:
            running_summary_parts.append(f"[{title}] {summary}")

    _chapters[asset_id] = chapters
    return {
        "chapters_completed": successful_chapters,
        "fallback_used_count": fallback_count,
        "provider_used": provider,
        "model_used": model,
        "skill_applications_count": total_skill_applications,
        "volumes_count": sum(1 for s in chapter_specs if s.get("depth") == 0),
    }


def order_idx_to_vol_idx(chapter_specs: list[dict], order_idx: int) -> int:
    """根据 order_index 找到这是第几个卷 (从 0 起)."""
    vol_count = 0
    for i, spec in enumerate(chapter_specs):
        if spec.get("depth") == 0:
            if i == order_idx:
                return vol_count
            vol_count += 1
    return vol_count - 1 if vol_count > 0 else 0


def _truncate_summary(parts: list[str]) -> str:
    """从末尾往前累加 parts, 不超过 _BOOK_SUMMARY_MAX_CHARS."""
    if not parts:
        return "(本章为开篇, 无前文)"
    out: list[str] = []
    total = 0
    for p in reversed(parts):
        if total + len(p) > _BOOK_SUMMARY_MAX_CHARS and out:
            break
        out.append(p)
        total += len(p)
    return "\n".join(reversed(out))


async def _call_book_chapter_llm(
    book_title: str,
    volume_title: str,
    chapter_title: str,
    running_summary: str,
    project_id: str,
    provider: str,
    model: str,
    skill_suffix: str = "",
) -> dict[str, Any]:
    tpl = PromptTemplate.load("content/book")
    rendered = tpl.render({
        "book_title": book_title,
        "volume_title": volume_title,
        "chapter_title": chapter_title,
        "running_summary": running_summary,
    })
    system_prompt = rendered.system
    if skill_suffix:
        system_prompt = f"{system_prompt}\n\n{skill_suffix}"
    router = await get_router()
    try:
        response = await router.generate(
            task="book",
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=rendered.user),
            ],
            options=LLMOptions(**rendered.options),
            project_id=project_id,
            provider_override=provider,
            model_override=model,
        )
        content = response.text.strip()
        if len(content) < 80:
            raise ValueError(f"book 章节返回过短: {content!r}")
        return {
            "content": content,
            "usage": response.usage,
            "fallback_used": response.fallback_used,
            "latency_ms": response.latency_ms,
        }
    except Exception as exc:
        logger.warning("book_chapter_llm_failed", title=chapter_title, error=str(exc))
        return {
            "content": _placeholder_content(chapter_title, "book"),
            "usage": {},
            "fallback_used": True,
            "latency_ms": 0,
        }


async def _summarize_book_chapter(
    chapter_title: str,
    chapter_content: str,
    project_id: str,
) -> str:
    tpl = PromptTemplate.load("content/book_summarize")
    rendered = tpl.render({
        "chapter_title": chapter_title,
        "chapter_content": chapter_content[:4000],  # 截断防爆
    })
    router = await get_router()
    response = await router.generate(
        task="book",
        messages=[
            LLMMessage(role="system", content=rendered.system),
            LLMMessage(role="user", content=rendered.user),
        ],
        options=LLMOptions(**rendered.options),
        project_id=project_id,
    )
    return response.text.strip()[:250]


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
    """阶段 4 · 证据链回填 · embedding cosine 重排.

    流程:
        1. 拉 project 最近 30 天 events (limit 300)
        2. 批量 embed (nomic-embed-text:latest, 768d): events + chapters
        3. 每章 cosine 排序, 取 top-4 (强制 ≥2 个 source_type 多样性)
        4. citation_strength = 真 cosine score (而非 random)

    fallback:
        - 没真 events → reason=no_events
        - embedding 调用失败 → 回退到跨源 round-robin (现 _pick_diverse_events)
    """
    import random
    from app.llm_gateway.embedding import EmbeddingError, cosine, embed_batch

    asset = _assets[asset_id]
    db = get_db()
    week_ago_30 = (_now() - timedelta(days=30)).isoformat()

    all_events, _ = db.list_events(
        project_id=asset.project_id,
        from_iso=week_ago_30,
        limit=300,
    )
    if not all_events:
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

    chapters = _chapters.get(asset_id, [])
    if not chapters:
        return {"evidence_total": 0, "fallback_used": True, "chapters_with_evidence": 0}

    # ── 1. 准备 embedding 文本 ─────────────────────────────
    event_texts = [_event_to_embed_text(e) for e in all_events]
    chapter_texts = [_chapter_to_embed_text(c) for c in chapters]

    # ── 2. 批量 embed ─────────────────────────────────────
    use_embedding = True
    event_vecs: list[list[float]] = []
    chapter_vecs: list[list[float]] = []
    try:
        # 一次 batch 同时 embed events + chapters, 减少模型加载次数
        combined = await embed_batch(event_texts + chapter_texts)
        event_vecs = combined[: len(event_texts)]
        chapter_vecs = combined[len(event_texts) :]
        logger.info(
            "evidence_embedding_done",
            asset_id=asset_id,
            events=len(event_vecs),
            chapters=len(chapter_vecs),
        )
    except EmbeddingError as e:
        logger.warning(
            "evidence_embedding_failed_fallback",
            asset_id=asset_id, error=str(e),
        )
        use_embedding = False

    # ── 3. 为每章选 top-4 (final = 0.6×cos + 0.25×trust + 0.15×recency) ──
    by_source: dict[str, list[dict]] = {}
    for e in all_events:
        by_source.setdefault(e.get("source_type", "other"), []).append(e)

    # 预算 recency: 越新分越高 (30 天衰减一半)
    now_utc = _now()
    event_recency: list[float] = []
    for e in all_events:
        event_recency.append(_compute_recency(e.get("occurred_at"), now_utc))

    # event trust (插件上报的真值, 没有的 fallback 到 source_type 默认)
    event_trust: list[float] = []
    for e in all_events:
        t = e.get("trust_score")
        if t is None:
            t = {"github": 0.85, "claude_code": 0.75, "cursor": 0.70}.get(
                e.get("source_type", ""), 0.60
            )
        event_trust.append(float(t))

    total_evidence = 0
    avg_cos_per_chapter: list[float] = []
    avg_final_per_chapter: list[float] = []
    for ch_idx, ch in enumerate(chapters):
        num = 4
        if use_embedding:
            ch_vec = chapter_vecs[ch_idx]
            scored: list[tuple[float, float, float, dict]] = []
            for i, ev_vec in enumerate(event_vecs):
                cos_v = cosine(ch_vec, ev_vec)
                # final = 综合分; 各分量保留方便调试
                trust = event_trust[i]
                rec = event_recency[i]
                final = 0.6 * cos_v + 0.25 * trust + 0.15 * rec
                scored.append((final, cos_v, trust, all_events[i]))
            scored.sort(key=lambda x: x[0], reverse=True)
            top = scored[:num]
            chosen_with_score = _enforce_source_diversity_scored(scored, num)
            avg_cos_per_chapter.append(
                round(sum(c for _, c, _, _ in top) / num, 3)
            )
            avg_final_per_chapter.append(
                round(sum(f for f, _, _, _ in top) / num, 3)
            )
        else:
            # fallback: 现 round-robin · 没有打分信息
            chosen_with_score = [
                (0.0, 0.0, ev.get("trust_score") or 0.7, ev)
                for ev in _pick_diverse_events(by_source, num)
            ]
            avg_cos_per_chapter.append(0.0)
            avg_final_per_chapter.append(0.0)

        ev_list: list[Evidence] = []
        content_len = max(50, len(ch.content))
        for idx, (final_score, cos_score, trust, ev_raw) in enumerate(chosen_with_score):
            span_start = random.randint(0, max(1, content_len - 50))
            span_end = min(content_len, span_start + random.randint(20, 50))
            ev_list.append(
                _build_evidence_from_event(
                    ev_raw, ch.id, idx, span_start, span_end,
                    cosine_score=cos_score if use_embedding else None,
                    composite_score=final_score if use_embedding else None,
                )
            )
        _evidence_by_chapter[ch.id] = ev_list
        total_evidence += len(ev_list)

        # T07-fix · 后处理 chapter content 的 [N] 标签:
        # LLM 经常输出跳号 / 超量 (例如 [1][3][5] 或 [1]..[7] 但只 4 evidence)
        # 统一重编号 [1..len(ev_list)] 按出现顺序, 超出的标签删掉避免死链.
        if ch.content and ev_list:
            normalized, tag_count = _normalize_evidence_tags(ch.content, len(ev_list))
            if normalized != ch.content:
                logger.info(
                    "chapter_tags_normalized",
                    asset_id=asset_id,
                    chapter_id=ch.id,
                    tags_in_content=tag_count,
                    evidence_count=len(ev_list),
                )
                ch.content = normalized

    logger.info(
        "evidence_reranked",
        asset_id=asset_id,
        events_in_window=len(all_events),
        sources=list(by_source.keys()),
        total_evidence=total_evidence,
        method="embedding_cosine_trust_recency" if use_embedding else "round_robin_fallback",
        avg_cosine_per_chapter=avg_cos_per_chapter,
        avg_final_per_chapter=avg_final_per_chapter,
        weights={"cosine": 0.6, "trust": 0.25, "recency": 0.15},
    )
    return {
        "evidence_total": total_evidence,
        "evidence_stale": 0,
        "fallback_used": not use_embedding,
        "chapters_with_evidence": len(chapters),
        "real_event_pool_size": len(all_events),
        "rerank_method": "cosine_trust_recency" if use_embedding else "round_robin",
        "avg_cosine_per_chapter": avg_cos_per_chapter,
        "avg_final_per_chapter": avg_final_per_chapter,
        "weights": {"cosine": 0.6, "trust": 0.25, "recency": 0.15},
    }


def _compute_recency(occurred_at: str | None, now: datetime) -> float:
    """时间衰减 0-1. 0 天=1.0, 30 天≈0.5, 90 天≈0.13."""
    if not occurred_at:
        return 0.5
    try:
        # 容 ISO 8601 + Z 后缀
        ts = occurred_at.replace("Z", "+00:00") if occurred_at.endswith("Z") else occurred_at
        ev_dt = datetime.fromisoformat(ts)
        if ev_dt.tzinfo is None:
            ev_dt = ev_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.5
    days = max(0.0, (now - ev_dt).total_seconds() / 86400.0)
    # 半衰期 30 天: exp(-days * ln(2) / 30)
    import math
    return round(math.exp(-days * 0.6931 / 30.0), 3)


def _enforce_source_diversity_scored(
    scored: list[tuple[float, float, float, dict]], num: int, min_sources: int = 2,
) -> list[tuple[float, float, float, dict]]:
    """同 _enforce_source_diversity 但 tuple 是 4 元 (final, cos, trust, event)."""
    if not scored:
        return []
    out = list(scored[:num])
    sources_in_top = {item[3].get("source_type") for item in out}
    if len(sources_in_top) >= min_sources:
        return out
    dominant = next(iter(sources_in_top))
    for s_final, s_cos, s_trust, e in scored[num:]:
        if e.get("source_type") != dominant:
            out[-1] = (s_final, s_cos, s_trust, e)
            break
    return out


def _event_to_embed_text(e: dict) -> str:
    """events 表的 dict → 给 embedding 的文本.

    用 title + 前 500 字内容, 含 source_type 提高跨源区分.
    """
    title = e.get("title") or ""
    content = (e.get("content") or "")[:500]
    src = e.get("source_type", "")
    return f"[{src}] {title}\n\n{content}"


# 角标正则: 匹配独立的 [数字], 不会吃掉 markdown 链接 [text](url) 或 [text][ref]
# 用负向后查避免 ![alt](src) 那种图片语法
_EVIDENCE_TAG_RE = re.compile(r"(?<!\!)\[(\d+)\](?!\(|\[)")


def _normalize_evidence_tags(content: str, k: int) -> tuple[str, int]:
    """把 chapter content 里的 [N] 标签重编号为 [1..k] 按出现顺序.

    - LLM 经常输出 [1] [3] [5] 这种跳号, 或 [1] [2] [3] [4] [5] 超量
    - k 是本章可用 evidence 数, 取 len(ev_list)
    - 超过 k 的标签会被静默去掉 (没有对应 evidence 时不留死链)
    - 不动 markdown 链接 [text](url) / 引用 [ref][1]

    返回 (new_content, found_count) — found_count 是发现的 [N] 数量, 调试用.
    """
    if k <= 0:
        # 没 evidence, 把所有 [N] 都剥掉, 不留死链
        cleaned = _EVIDENCE_TAG_RE.sub("", content)
        return cleaned, 0

    count = 0

    def _replace(_m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        if count <= k:
            return f"[{count}]"
        return ""  # 超过 k 的标签直接删, 避免点了 [5] 找不到证据

    new_content = _EVIDENCE_TAG_RE.sub(_replace, content)
    return new_content, count


def _chapter_to_embed_text(ch: "Chapter") -> str:
    """章节 → embedding 文本 (标题 + 前 500 字)."""
    return f"{ch.title}\n\n{(ch.content or '')[:500]}"


def _enforce_source_diversity(
    scored: list[tuple[float, dict]], num: int, min_sources: int = 2,
) -> list[tuple[float, dict]]:
    """按 cosine 排序取 top-N, 但若 top-N 全 1 个 source_type, 强行换 1 条进来.

    e.g. cosine top-4 全 github → 把第 4 名换成 cosine 最高的非 github 那条.
    """
    if not scored:
        return []
    out = list(scored[:num])
    sources_in_top = {item[1].get("source_type") for item in out}
    if len(sources_in_top) >= min_sources:
        return out
    # 找一个外族最佳
    dominant_source = next(iter(sources_in_top))
    for s, e in scored[num:]:
        if e.get("source_type") != dominant_source:
            out[-1] = (s, e)
            break
    return out


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
    cosine_score: float | None = None,
    composite_score: float | None = None,
) -> Evidence:
    """从真 events 表的 row dict 构 Evidence.

    cosine_score: 章节 vs event 的 embedding cosine, 用作 citation_strength
    composite_score: cosine + trust + recency 综合分, payload 调试用
    """
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
    # event 自己的 trust_score (插件上报的真值); 没有 fallback 到 source_type
    trust_score = event.get("trust_score")
    if trust_score is None:
        st = event.get("source_type", "")
        trust_score = {"github": 0.85, "claude_code": 0.75, "cursor": 0.70}.get(st, 0.60)
    # citation_strength: 用真 cosine 优先 (0-1), 没有则按 trust_score × 噪声
    if cosine_score is not None:
        citation_strength = round(max(0.0, min(1.0, cosine_score)), 3)
    else:
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
    """阶段 5 · 自评卡 · 真指标 + 1 次 LLM 评估.

    指标派生:
      - coverage          = avg( min(len(evidence)/4, 1.0) ) 跨章节
      - citation_density  = avg_cosine_per_chapter (取 evidence 阶段记录的真 cosine)
      - slop_score        = LLM 评估全文空话比例 (1 JSON call, 0=好/1=差)
      - similarity        = 与同项目历史 asset outline 的最大 cosine
                            (无历史时 0; high = 可能重复劳动)

    fallback:
      - LLM 评 slop 失败 → 启发式 (短句比例 + 模板词频)
      - embedding 失败 (evidence stage 没记录 cosine) → 用 trust_score 均值代替
      - similarity embedding 失败 → 0.0 + method="embedding_unavailable"

    v1.2 · type=knowledge_graph 走专属 assess (dedup + 双向化 + 图指标),
    不复用 markdown-based 的 4 指标计算.
    """
    if req.type == "knowledge_graph":
        return await _stage_assess_knowledge_graph(asset_id, req)

    asset = _assets[asset_id]
    chapters = _chapters.get(asset_id, [])
    progress = _progress[asset_id]

    # ── 1. coverage: evidence 数 ÷ 目标 ────────────────────────
    target_per_chapter = 4
    coverage_components: list[float] = []
    for ch in chapters:
        ev_list = _evidence_by_chapter.get(ch.id, [])
        ratio = min(len(ev_list) / target_per_chapter, 1.0)
        coverage_components.append(ratio)
    coverage = (
        round(sum(coverage_components) / len(coverage_components), 3)
        if coverage_components else 0.0
    )

    # ── 2. citation_density: 用 evidence 阶段保存的 avg_cosine ─
    citation_density = 0.0
    try:
        ev_idx = _stage_index(progress, "evidence")
        ev_meta = progress.stages[ev_idx].metadata or {}
        cos_per_ch = ev_meta.get("avg_cosine_per_chapter") or []
        if cos_per_ch:
            citation_density = round(sum(cos_per_ch) / len(cos_per_ch), 3)
        elif chapters:
            # embedding 失败 fallback: 用 evidence trust_score 均值
            all_trust = [
                ev.trust_score or 0.7
                for ch in chapters
                for ev in _evidence_by_chapter.get(ch.id, [])
            ]
            if all_trust:
                citation_density = round(sum(all_trust) / len(all_trust), 3)
    except (IndexError, KeyError, ValueError):
        citation_density = 0.0

    # ── 3. slop_score: LLM 评全文空话比例 ─────────────────────
    slop_score, slop_method, slop_reasoning = await _assess_slop_via_llm(
        asset, chapters, req
    )

    # ── 4. similarity: 与项目内历史资产的最大余弦相似度 ──────────
    #
    # 语义: "本文档是否和过去某份发过的报告高度重合 (=可能是重复劳动 / 自我抄袭)".
    # 公式: similarity = max( cos(outline_emb(current), outline_emb(prior_i)) )
    #       outline_emb = "title\n章节标题1\n章节首段...\n章节标题N\n章节首段..."
    # 边界:
    #   - 项目内没有其它 asset → 0.0
    #   - embedding 失败 → 0.0 + method="unavailable"
    similarity, sim_method, sim_most_similar_id = await _compute_similarity_to_history(
        asset, chapters,
    )

    # ── 5. consistency_score (v0.2 · 仅 book): 跨章节连贯度 ─────
    #
    # 语义: book 长文档相邻章节的语义衔接度. 高=承上启下顺畅, 低=主题跳跃.
    # 公式: avg( cosine(emb(ch_i), emb(ch_{i+1})) ) 跨同卷内相邻 depth=1 章节
    # 仅在 type=book 时计算; 其它类型 None.
    consistency_score: float | None = None
    consistency_method = "skipped"
    if req.type == "book" and chapters:
        consistency_score, consistency_method = await _compute_book_consistency(chapters)

    metrics = AssetMetrics(
        coverage=coverage,
        citation_density=citation_density,
        slop_score=slop_score,
        similarity=similarity,
        consistency_score=consistency_score,
    )
    asset.metrics = metrics
    asset.status = "draft"
    asset.current_version = 1
    asset.updated_at = _now()

    logger.info(
        "assess_done",
        asset_id=asset_id,
        coverage=coverage,
        citation_density=citation_density,
        slop_score=slop_score,
        slop_method=slop_method,
        similarity=similarity,
        sim_method=sim_method,
        most_similar_to=sim_most_similar_id,
        chapters=len(chapters),
    )
    result = metrics.model_dump()
    result["_method"] = {
        "coverage": "evidence_count_ratio",
        "citation_density": "avg_cosine_per_chapter"
        if citation_density and "avg_cosine_per_chapter" in (
            progress.stages[_stage_index(progress, "evidence")].metadata or {}
        ) else "trust_score_fallback",
        "slop_score": slop_method,
        "similarity": sim_method,
    }
    result["_slop_reasoning"] = slop_reasoning
    if sim_most_similar_id:
        result["_most_similar_asset_id"] = sim_most_similar_id
    if consistency_score is not None:
        result["_method"]["consistency_score"] = consistency_method
    return result


async def _compute_book_consistency(
    chapters: list["Chapter"],
) -> tuple[float | None, str]:
    """v0.2 · book 跨章一致性: 同卷内相邻 depth=1 章节的 cosine 均值.

    实现:
      1. 按 parent_id 分组 (同卷的章在一起)
      2. 对每组内相邻章 (i, i+1) 抽 content 首 800 字符做 embedding
      3. 计算所有相邻对的 cosine 均值

    边界:
      - 组内只有 1 个章节 → 不算
      - embedding 失败 → 返回 None + method="embedding_unavailable"
      - 无任何相邻对 → 返回 None + method="no_pairs"
    """
    from app.llm_gateway.embedding import EmbeddingError, cosine, embed_batch

    # 按卷 (parent_id) 分组, 只看 depth=1 子章节
    groups: dict[str, list["Chapter"]] = {}
    for ch in chapters:
        if (ch.depth or 0) != 1 or not ch.parent_id:
            continue
        groups.setdefault(ch.parent_id, []).append(ch)
    # 按 order_index 排序
    for g in groups.values():
        g.sort(key=lambda c: c.order_index)

    # 收集相邻对的文本 (各取首 800 字)
    pair_texts: list[tuple[str, str]] = []
    for chs in groups.values():
        for i in range(len(chs) - 1):
            a = (chs[i].content or "")[:800]
            b = (chs[i + 1].content or "")[:800]
            if a and b:
                pair_texts.append((a, b))

    if not pair_texts:
        return None, "no_pairs"

    # 一次性 embed 所有文本 (a + b interleaved)
    flat_texts: list[str] = []
    for a, b in pair_texts:
        flat_texts.append(a)
        flat_texts.append(b)
    try:
        vectors = await embed_batch(flat_texts)
    except EmbeddingError as e:
        logger.warning("book_consistency_embed_failed", error=str(e))
        return None, "embedding_unavailable"
    if len(vectors) != len(flat_texts):
        return None, "embedding_unavailable"

    sims: list[float] = []
    for i, _pair in enumerate(pair_texts):
        sims.append(cosine(vectors[2 * i], vectors[2 * i + 1]))
    avg = sum(sims) / len(sims) if sims else 0.0
    return round(avg, 3), "adjacent_chapter_cosine"


def _build_outline_text(title: str, chapters: list["Chapter"]) -> str:
    """把 asset outline 拼成 embedding 输入. 拍上限 1500 字符避免长尾."""
    parts: list[str] = [title or ""]
    for ch in chapters:
        parts.append(ch.title or "")
        # 章节首段 (前 200 字符) — 比纯标题信号丰富, 又不会被超长正文淹没
        head = (ch.content or "").strip().split("\n", 1)[0][:200]
        if head:
            parts.append(head)
    text = "\n".join(p for p in parts if p)
    return text[:1500]


async def _compute_similarity_to_history(
    asset: Asset,
    chapters: list["Chapter"],
) -> tuple[float, str, str | None]:
    """与同项目内其它 asset 的最大余弦相似度.

    返回 (similarity, method, most_similar_asset_id).
      method ∈ "max_cosine_to_history" / "no_history" / "embedding_unavailable"
    """
    # 同项目其它 asset (排除自身)
    prior_assets = [
        a for a in _assets.values()
        if a.project_id == asset.project_id and a.id != asset.id
    ]
    if not prior_assets:
        return 0.0, "no_history", None

    current_text = _build_outline_text(asset.title, chapters)
    if not current_text:
        return 0.0, "no_history", None

    # 拼 prior outlines (取每个 asset 的 chapters)
    prior_texts: list[tuple[str, str]] = []   # (asset_id, text)
    for a in prior_assets:
        a_chs = _chapters.get(a.id, [])
        if not a_chs:
            continue
        txt = _build_outline_text(a.title, a_chs)
        if txt:
            prior_texts.append((a.id, txt))
    if not prior_texts:
        return 0.0, "no_history", None

    # 一次性 embedding (current + N prior)
    try:
        from app.llm_gateway.embedding import embed_batch, cosine
        texts = [current_text] + [t for _, t in prior_texts]
        vectors = await embed_batch(texts)
    except Exception as e:  # noqa: BLE001
        logger.warning("similarity_embedding_failed", error=str(e))
        return 0.0, "embedding_unavailable", None

    if not vectors or len(vectors) < 2:
        return 0.0, "embedding_unavailable", None

    current_vec = vectors[0]
    best_cos = 0.0
    best_id: str | None = None
    for (aid, _), vec in zip(prior_texts, vectors[1:], strict=True):
        try:
            c = cosine(current_vec, vec)
        except Exception:  # noqa: BLE001
            continue
        if c > best_cos:
            best_cos = c
            best_id = aid

    return round(best_cos, 3), "max_cosine_to_history", best_id


async def _assess_slop_via_llm(
    asset: Asset,
    chapters: list["Chapter"],
    req: GenerateAssetRequest,
) -> tuple[float, str, str]:
    """1 次 LLM 调用评全文 slop_score (0..1, 低=好).

    返回 (slop_score, method, reasoning)
      method ∈ "llm" / "heuristic_fallback"
    """
    if not chapters:
        return 0.0, "no_chapters", "no chapters to assess"

    # 拼章节摘要 (前 200 字/章), 避免 prompt 过长
    digest_parts = []
    for ch in chapters[:8]:   # 最多 8 章
        snippet = (ch.content or "")[:200].replace("\n", " ").strip()
        digest_parts.append(f"## {ch.title}\n{snippet}")
    digest = "\n\n".join(digest_parts)

    # A1.2: 抽 prompt 到 app/prompts/assess/_default.md.
    tpl = PromptTemplate.load("assess/_default")
    rendered = tpl.render({
        "asset_type": asset.type,
        "title": asset.title,
        "digest": digest,
    })
    system_prompt = rendered.system
    user_prompt = rendered.user

    router = await get_router()
    try:
        # 复用 asset.type 的 provider 路由 (assess 不另设独立任务键)
        # 不开 json_mode: ollama 的 reasoning 模型 (minimax-m2) 开了反而返回空
        response = await router.generate(
            task=asset.type,
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            options=LLMOptions(**rendered.options),
            project_id=asset.project_id,
        )
        text = response.text.strip()
        if not text:
            raise ValueError("LLM 返回空 text")
        # 容错 1: 去掉可能的 markdown 代码块包裹
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
        # 容错 2: 模型在 JSON 前后塞了说明文字 → 提取第一个 { ... } 块
        m = re.search(r"\{[^{}]*\"slop_score\"[^{}]*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
        parsed = json.loads(text)
        score = float(parsed.get("slop_score", 0.5))
        score = max(0.0, min(1.0, score))   # clamp 0..1
        reasoning = str(parsed.get("reasoning", ""))[:80]
        return round(score, 3), "llm", reasoning
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
        logger.warning(
            "assess_slop_llm_parse_failed_fallback",
            asset_id=asset.id, error=str(e),
        )
    except Exception as e:
        logger.warning(
            "assess_slop_llm_failed_fallback",
            asset_id=asset.id, error=str(e),
        )

    # heuristic fallback: 统计模板套话词频 / 总词
    cliches = (
        "本周", "我们将", "高效推进", "稳步推进", "积极", "切实",
        "持续优化", "进一步", "通过努力", "团队齐心", "成效显著",
        "顺利完成", "圆满", "充分", "深入", "全面",
    )
    all_text = "\n".join((c.content or "") for c in chapters)
    if not all_text:
        return 0.5, "heuristic_fallback", "no content"
    cliche_count = sum(all_text.count(c) for c in cliches)
    # 估算每 100 字模板词数 → slop 0..1
    per_100 = cliche_count / max(1, len(all_text) / 100)
    score = min(1.0, per_100 / 5.0)   # 5/100 字 = 满 slop
    return round(score, 3), "heuristic_fallback", f"cliches={cliche_count}"


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
    trigger_meta: dict | None = None,
) -> Asset:
    """触发文档生成. 立即返回 Asset (status=generating), 后台跑 5 阶段.

    Args:
        trigger_meta: v0.4 自动触发标记 (None=手动生成); 非空时直接写入
            asset.trigger_meta, 让 UI 显示 🤖 徽标 + 可解释卡 (体验要素 #33/#34).
    """
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
        trigger_meta=trigger_meta,
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
        "book": "技术书籍",
        "agent_skill": "Agent 专家技能",
    }[asset.type]

    # A1.3: 抽 prompt 到 app/prompts/regenerate/_default.md.
    tpl = PromptTemplate.load("regenerate/_default")
    rendered = tpl.render({
        "type_label": type_label,
        "chapter_title": chapter.title,
        "chapter_content": chapter.content,
        "instruction": instruction,
    })

    router = await get_router()
    response = await router.generate(
        task=asset.type,
        messages=[
            LLMMessage(role="system", content=rendered.system),
            LLMMessage(role="user", content=rendered.user),
        ],
        options=LLMOptions(**rendered.options),
        project_id=asset.project_id,
        user_id=user_id,
        provider_override=provider,
        model_override=model,
    )
    new_content = response.text.strip()
    if len(new_content) < 30:
        raise ValueError(f"LLM 返回内容过短: {new_content!r}")

    # T07-fix · 重生成后的 content 也要规范化 [N] 角标, 否则会和已有 evidence 错位
    existing_evidence = _evidence_by_chapter.get(chapter_id, [])
    if existing_evidence:
        new_content, _ = _normalize_evidence_tags(new_content, len(existing_evidence))

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

    # v0.2 · 隐式反馈: 重生成 diff 比例反映用户对当前 skill 的认可度
    # 大改 (> 50% 内容变更) → rejected 信号; 小改 → approved 信号
    _notify_skill_feedback_regen(chapter, previous_content, new_content)

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
    """返回 project 下所有 assets, 按 created_at desc 排序 (最新在前).

    Bug fix 2026-05-22: 之前返回 dict 插入顺序, 新生成的 asset 排在末尾,
    用户在前 N 个卡片里看不到, 误以为"生成没工作". 现按 created_at 倒序.
    """
    items = [a for a in _assets.values() if a.project_id == project_id]
    return sorted(items, key=lambda a: a.created_at, reverse=True)


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
    """T09 · 章节级通过. 全部通过时把 asset.approval_state 升 approved + status review→approved.

    v0.2 · 反馈给应用的 skill: action=approved 累加 acceptance_count.
    """
    chapter = _find_chapter(asset_id, chapter_id)
    if chapter is None:
        return None
    chapter.approval_state = "approved"
    _refresh_asset_approval(asset_id)
    _persist_asset(asset_id)   # P1
    _notify_skill_feedback(chapter, action="approved")
    return chapter


def reject_chapter(asset_id: str, chapter_id: str, reason: str) -> Chapter | None:
    """T09 · 章节级退回. 任一章节退回时 asset.approval_state = 'rejected'.

    v0.2 · 反馈给应用的 skill: action=rejected 累加 rejection_count.
    """
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
    _notify_skill_feedback(chapter, action="rejected")
    return chapter


def _notify_skill_feedback(chapter: Chapter, action: str) -> None:
    """v0.2 · 把章节状态变化转发给 skill_service.

    chapter.applied_skills 为空时 (4 类老文档或未注入) 直接返回.
    """
    if not getattr(chapter, "applied_skills", None):
        return
    try:
        from app.services import skill_service  # 延迟 import 避免循环
        skill_service.on_chapter_state_changed(
            chapter_id=chapter.id,
            applied_skill_records=list(chapter.applied_skills),
            action=action,
        )
    except Exception as exc:
        logger.warning(
            "skill_feedback_notify_failed",
            chapter_id=chapter.id,
            action=action,
            error=str(exc),
        )


_REGEN_BIG_DIFF_THRESHOLD = 0.5
"""regenerate 后 字符 diff 比例 > 此值 → 大改 (rejected 信号)."""


def _notify_skill_feedback_regen(
    chapter: Chapter, old_content: str, new_content: str
) -> None:
    """v0.2 · regenerate 隐式反馈: diff 大 = skill 没用对, diff 小 = skill 帮上忙."""
    if not getattr(chapter, "applied_skills", None):
        return
    if not old_content:
        return
    # 简单字符级 diff 比例 (避免依赖 difflib 重量库)
    base_len = max(len(old_content), len(new_content))
    if base_len == 0:
        return
    # 计算最长公共前缀 / 后缀以估算变更比例 (近似但快)
    common_prefix = _common_prefix_len(old_content, new_content)
    common_suffix = _common_suffix_len(old_content, new_content)
    unchanged = common_prefix + common_suffix
    diff_ratio = max(0.0, 1.0 - unchanged / base_len)
    action = (
        "regen_big_diff" if diff_ratio > _REGEN_BIG_DIFF_THRESHOLD
        else "regen_small_diff"
    )
    _notify_skill_feedback(chapter, action=action)


def _common_prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def _common_suffix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[-1 - i] == b[-1 - i]:
        i += 1
    return i


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
