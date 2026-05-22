"""Book 两步大纲 + 滚动 summary content (v0.2 Milestone B).

覆盖:
- _stage_outline_book 卷 + 章两步生成 (mock LLM)
- volume_outline_completed + chapter_outline_completed SSE 事件
- 卷 LLM 失败 → fallback specs
- 章 LLM 失败 → 单卷 fallback
- _book_fallback_specs 兜底结构
- _truncate_summary 字符数边界
- order_idx_to_vol_idx 卷索引映射
- _stage_content_book sequential + rolling_summary + parent_id 链接
- _call_book_chapter_llm 滚动 summary 注入
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.asset import Asset
from app.schemas.generation import (
    GenerateAssetRequest,
    GenerationProgress,
    StageStatus,
)
from app.services import generation_service, skill_service


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    skill_service.reset_registry_for_tests()
    generation_service._assets.clear()
    generation_service._chapters.clear()
    generation_service._progress.clear()
    generation_service._evidence_by_chapter.clear()
    generation_service._sse_queues.clear()
    yield new_store


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_book_asset(asset_id: str = "a1", project_id: str = "p1") -> Asset:
    asset = Asset(
        id=asset_id, project_id=project_id, type="book",
        title="TokenKnows 内部架构手册",
        status="generating", current_version=1, template_id=None,
        created_by="u", created_at=_now(), updated_at=_now(),
    )
    generation_service._assets[asset_id] = asset
    generation_service._progress[asset_id] = generation_service._initial_progress(asset_id)
    return asset


class _BookRouter:
    """Mock LLM router: 卷大纲 + 每卷章大纲 + 章内容 + 摘要 队列."""

    def __init__(
        self,
        volume_response: str,
        chapter_responses: list[str],
        content_response: str = "本章内容,详细讨论...\n\n## 小节1\n这里写了 PR #123 与 Issue #45 的具体讨论与决策过程。" * 5,
        summary_response: str = "本章总结: 介绍了背景与关键概念,引用 PR #123 / Issue #45.",
    ) -> None:
        self.volume_response = volume_response
        self.chapter_responses = list(chapter_responses)
        self.content_response = content_response
        self.summary_response = summary_response
        self.calls: list[dict] = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        sys_prompt = kwargs.get("messages", [None])[0]
        text = sys_prompt.content if sys_prompt else ""
        if "顶层「卷」大纲" in text:
            payload = self.volume_response
        elif "「章」级大纲" in text:
            payload = self.chapter_responses.pop(0) if self.chapter_responses else "{}"
        elif "≤ 200 字摘要" in text:
            payload = self.summary_response
        else:
            payload = self.content_response
        return type("Resp", (), {
            "text": payload,
            "provider": "anthropic",
            "model_used": "claude",
            "usage": {"prompt_tokens": 100, "completion_tokens": 200},
            "fallback_used": False,
            "latency_ms": 50,
        })()


# ─── _stage_outline_book ────────────────────────────────────


@pytest.mark.asyncio
async def test_outline_book_two_step_happy_path() -> None:
    _seed_book_asset()
    fake = _BookRouter(
        volume_response=json.dumps({"volumes": [
            {"title": "卷一 · 概述", "description": "讨论范围"},
            {"title": "卷二 · 实现", "description": "实现细节"},
        ]}),
        chapter_responses=[
            json.dumps({"chapters": ["第一章 · 背景", "第二章 · 概念", "第三章 · 范围"]}),
            json.dumps({"chapters": ["第一章 · 架构", "第二章 · 模块", "第三章 · 部署"]}),
        ],
    )
    with patch(
        "app.services.generation_service.get_router",
        new=AsyncMock(return_value=fake),
    ):
        result = await generation_service._stage_outline_book(
            "a1",
            GenerateAssetRequest(type="book", time_window="last_30_days"),
        )
    # 2 卷 × 3 章 + 2 卷自身 = 8
    assert result["chapters_total"] == 8
    specs = result["chapter_specs"]
    # 卷 / 章交替: 1 卷 → 3 章 → 1 卷 → 3 章
    assert specs[0]["depth"] == 0
    assert specs[1]["depth"] == 1
    assert specs[1]["parent_volume_index"] == 0
    assert specs[4]["depth"] == 0
    assert specs[5]["parent_volume_index"] == 1


@pytest.mark.asyncio
async def test_outline_book_volume_llm_failure_falls_back() -> None:
    _seed_book_asset()

    async def fail_generate(**kwargs):
        raise RuntimeError("volume LLM 不可用")
    fake = type("R", (), {"generate": fail_generate})()
    with patch(
        "app.services.generation_service.get_router",
        new=AsyncMock(return_value=fake),
    ):
        result = await generation_service._stage_outline_book(
            "a1",
            GenerateAssetRequest(type="book", time_window="last_30_days"),
        )
    assert result.get("llm_fallback_to_template") is True
    specs = result["chapter_specs"]
    # 兜底有 3 卷
    vols = [s for s in specs if s["depth"] == 0]
    assert len(vols) == 3


@pytest.mark.asyncio
async def test_outline_book_chapter_llm_partial_failure_falls_back() -> None:
    """卷 LLM 成功但某卷的章 LLM 失败 → 该卷得到兜底章."""
    _seed_book_asset()
    # 第二卷返非 list
    fake = _BookRouter(
        volume_response=json.dumps({"volumes": [
            {"title": "卷一", "description": "x"},
            {"title": "卷二", "description": "y"},
        ]}),
        chapter_responses=[
            json.dumps({"chapters": ["c1", "c2", "c3"]}),
            "not-valid-json",  # 第二卷失败
        ],
    )
    with patch(
        "app.services.generation_service.get_router",
        new=AsyncMock(return_value=fake),
    ):
        result = await generation_service._stage_outline_book(
            "a1",
            GenerateAssetRequest(type="book", time_window="last_30_days"),
        )
    specs = result["chapter_specs"]
    vol2_chapters = [s for s in specs if s["parent_volume_index"] == 1]
    # 第二卷应得到 5 个兜底章
    assert len(vol2_chapters) == 5
    assert "待补充内容" in vol2_chapters[0]["title"]


@pytest.mark.asyncio
async def test_outline_book_publishes_sse_events() -> None:
    _seed_book_asset()
    fake = _BookRouter(
        volume_response=json.dumps({"volumes": [
            {"title": "卷一", "description": "x"},
            {"title": "卷二", "description": "y"},
        ]}),
        chapter_responses=[
            json.dumps({"chapters": ["c1", "c2", "c3"]}),
            json.dumps({"chapters": ["c1", "c2", "c3"]}),
        ],
    )
    events_seen: list[str] = []
    original_publish = generation_service._publish_event

    async def spy_publish(asset_id, event):
        events_seen.append(event.event)
        await original_publish(asset_id, event)

    with patch(
        "app.services.generation_service.get_router",
        new=AsyncMock(return_value=fake),
    ), patch(
        "app.services.generation_service._publish_event",
        new=spy_publish,
    ):
        await generation_service._stage_outline_book(
            "a1",
            GenerateAssetRequest(type="book", time_window="last_30_days"),
        )
    assert "volume_outline_completed" in events_seen
    assert events_seen.count("chapter_outline_completed") == 2


# ─── 辅助函数 ────────────────────────────────────────────────


def test_book_fallback_specs_structure() -> None:
    specs = generation_service._book_fallback_specs()
    vols = [s for s in specs if s["depth"] == 0]
    chs = [s for s in specs if s["depth"] == 1]
    assert len(vols) == 3
    assert len(chs) == 6
    # 每个章都属于一个卷
    for ch in chs:
        assert ch["parent_volume_index"] in {0, 1, 2}


def test_truncate_summary_empty() -> None:
    assert "开篇" in generation_service._truncate_summary([])


def test_truncate_summary_keeps_recent() -> None:
    """超过上限时, 保留最新部分."""
    parts = [f"part{i} " + "x" * 600 for i in range(5)]  # 每个 ~610 字
    out = generation_service._truncate_summary(parts)
    # 应包含最新的几个, 不超过 1500 字符 + 缓冲
    assert "part4" in out
    assert "part0" not in out


def test_truncate_summary_under_limit_keeps_all() -> None:
    parts = ["短摘要1", "短摘要2", "短摘要3"]
    out = generation_service._truncate_summary(parts)
    assert "短摘要1" in out
    assert "短摘要3" in out


def test_order_idx_to_vol_idx() -> None:
    specs = [
        {"depth": 0},  # idx 0 = 卷0
        {"depth": 1, "parent_volume_index": 0},
        {"depth": 1, "parent_volume_index": 0},
        {"depth": 0},  # idx 3 = 卷1
        {"depth": 1, "parent_volume_index": 1},
        {"depth": 0},  # idx 5 = 卷2
    ]
    assert generation_service.order_idx_to_vol_idx(specs, 0) == 0
    assert generation_service.order_idx_to_vol_idx(specs, 3) == 1
    assert generation_service.order_idx_to_vol_idx(specs, 5) == 2


# ─── _stage_content_book ────────────────────────────────────


@pytest.mark.asyncio
async def test_stage_content_book_links_parent_ids() -> None:
    """章 (depth=1) 的 parent_id 应指向所在卷的 chapter.id."""
    _seed_book_asset()
    # 把 outline 阶段产物注入 progress
    progress = generation_service._progress["a1"]
    outline_stage = next(s for s in progress.stages if s.name == "outline")
    outline_stage.metadata = {
        "chapter_specs": [
            {"title": "卷一", "depth": 0, "parent_volume_index": None},
            {"title": "第一章", "depth": 1, "parent_volume_index": 0},
            {"title": "卷二", "depth": 0, "parent_volume_index": None},
            {"title": "第一章", "depth": 1, "parent_volume_index": 1},
        ]
    }

    fake = _BookRouter(
        volume_response="{}",  # 不会触发
        chapter_responses=[],
    )
    with patch(
        "app.services.generation_service.get_router",
        new=AsyncMock(return_value=fake),
    ):
        result = await generation_service._stage_content_book(
            "a1",
            GenerateAssetRequest(type="book", time_window="last_30_days"),
        )
    chapters = generation_service._chapters["a1"]
    # 4 章, 2 卷 + 2 章
    assert len(chapters) == 4
    vol_chapters = [c for c in chapters if c.depth == 0]
    sub_chapters = [c for c in chapters if c.depth == 1]
    assert len(vol_chapters) == 2
    assert len(sub_chapters) == 2
    # 第一个子章 parent = 卷一 id
    assert sub_chapters[0].parent_id == vol_chapters[0].id
    # 第二个子章 parent = 卷二 id
    assert sub_chapters[1].parent_id == vol_chapters[1].id
    # 卷自身 parent_id = None
    assert vol_chapters[0].parent_id is None
    # successful_chapters 不计卷
    assert result["chapters_completed"] == 2
    assert result["volumes_count"] == 2


@pytest.mark.asyncio
async def test_stage_content_book_uses_rolling_summary() -> None:
    """第 N 章 prompt 应包含前面章节的摘要."""
    _seed_book_asset()
    progress = generation_service._progress["a1"]
    outline_stage = next(s for s in progress.stages if s.name == "outline")
    outline_stage.metadata = {
        "chapter_specs": [
            {"title": "卷一", "depth": 0, "parent_volume_index": None},
            {"title": "第一章", "depth": 1, "parent_volume_index": 0},
            {"title": "第二章", "depth": 1, "parent_volume_index": 0},
        ]
    }

    fake = _BookRouter(
        volume_response="{}",
        chapter_responses=[],
        summary_response="第一章的核心结论",
    )
    with patch(
        "app.services.generation_service.get_router",
        new=AsyncMock(return_value=fake),
    ):
        await generation_service._stage_content_book(
            "a1",
            GenerateAssetRequest(type="book", time_window="last_30_days"),
        )

    # fake.calls 顺序: 第一章 content + 第一章 summarize + 第二章 content + 第二章 summarize
    # 第三次调用 (第二章 content) 的 user prompt 应含第一章的 summary
    content_calls = [
        c for c in fake.calls
        if "章节" in c["messages"][1].content and "正文" not in c["messages"][0].content[:20]
    ]
    # 简单验证: 至少有 1 次调用的 user 包含「第一章」摘要
    has_summary_in_later_call = any(
        "第一章的核心结论" in c["messages"][1].content
        for c in fake.calls
    )
    assert has_summary_in_later_call


@pytest.mark.asyncio
async def test_stage_content_book_uses_fallback_specs_when_outline_missing() -> None:
    """outline 阶段没有 chapter_specs → 用 _book_fallback_specs."""
    _seed_book_asset()
    # 不注入任何 outline metadata
    fake = _BookRouter(volume_response="{}", chapter_responses=[])
    with patch(
        "app.services.generation_service.get_router",
        new=AsyncMock(return_value=fake),
    ):
        await generation_service._stage_content_book(
            "a1",
            GenerateAssetRequest(type="book", time_window="last_30_days"),
        )
    chapters = generation_service._chapters["a1"]
    # fallback 有 3 卷 + 6 章
    assert len(chapters) == 9
