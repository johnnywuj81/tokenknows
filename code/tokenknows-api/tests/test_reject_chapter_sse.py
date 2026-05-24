"""T129 · reject_chapter 推 SSE asset_chapter_rejected 事件给作者."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.schemas.asset import Asset, Chapter
from app.services import generation_service, notification_sse


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch):
    """每个 test 跑前清空 _assets/_chapters + reset SSE queues."""
    snap_a = dict(generation_service._assets)
    snap_c = dict(generation_service._chapters)
    generation_service._assets.clear()
    generation_service._chapters.clear()
    notification_sse.reset_for_tests()
    monkeypatch.setattr(generation_service, "_persist_asset", lambda _: None)
    yield
    generation_service._assets.clear()
    generation_service._chapters.clear()
    generation_service._assets.update(snap_a)
    generation_service._chapters.update(snap_c)
    notification_sse.reset_for_tests()


def _mk_asset_and_chapter(*, author: str = "alice", asset_id: str = "a1") -> tuple[Asset, Chapter]:
    asset = Asset(
        id=asset_id, project_id="p1", type="weekly_report", title="周报",
        status="in_review", current_version=1, template_id="t",
        created_by=author, approval_state="pending",
        redaction_state="all_confirmed", created_at=_now(), updated_at=_now(),
    )
    chapter = Chapter(
        id="c1", asset_id=asset_id, asset_version=1, order_index=2,
        title="风险与阻塞", content="...", layout={},
        generated_by=None, regeneration_history=[],
        approval_state="pending",
        created_at="", updated_at="",
    )
    generation_service._assets[asset_id] = asset
    generation_service._chapters[asset_id] = [chapter]
    return asset, chapter


@pytest.mark.asyncio
async def test_reject_chapter_publishes_sse_to_author() -> None:
    """订阅作者 SSE → reject_chapter 后 queue 收到 asset_chapter_rejected 事件."""
    asset, chapter = _mk_asset_and_chapter(author="alice")
    q = await notification_sse.subscribe("alice")

    result = generation_service.reject_chapter(asset.id, chapter.id, "测试理由")
    assert result is not None
    assert result.approval_state == "rejected"

    event = await asyncio.wait_for(q.get(), timeout=1.0)
    assert event.event == "asset_chapter_rejected"
    assert event.user_id == "alice"
    assert event.asset_id == "a1"
    assert event.extra is not None
    assert event.extra["chapter_id"] == "c1"
    assert event.extra["chapter_title"] == "风险与阻塞"
    assert event.extra["reason"] == "测试理由"
    assert event.extra["project_id"] == "p1"
    assert event.extra["order_index"] == 2


def test_reject_chapter_anonymous_author_no_publish() -> None:
    """anonymous 作者 → 不推 SSE (没人订阅), 不抛."""
    asset, chapter = _mk_asset_and_chapter(author="anonymous")
    queues_before = notification_sse.active_user_count()
    result = generation_service.reject_chapter(asset.id, chapter.id, "no-author test")
    assert result is not None
    assert notification_sse.active_user_count() == queues_before


def test_reject_chapter_no_subscribers_silently_zero_delivery() -> None:
    """作者非匿名但未订阅 → publish 返回 0, 主流程不抛."""
    asset, chapter = _mk_asset_and_chapter(author="bob")
    result = generation_service.reject_chapter(asset.id, chapter.id, "bob 没在线")
    assert result is not None
    assert result.approval_state == "rejected"


@pytest.mark.asyncio
async def test_sse_event_json_has_asset_id_field() -> None:
    """T129 · to_json 序列化应包含 asset_id 字段, 给前端解析用."""
    asset, chapter = _mk_asset_and_chapter(author="carol")
    q = await notification_sse.subscribe("carol")
    generation_service.reject_chapter(asset.id, chapter.id, "json shape check")
    event = await asyncio.wait_for(q.get(), timeout=1.0)
    import json
    payload = json.loads(event.to_json())
    assert payload["event"] == "asset_chapter_rejected"
    assert payload["asset_id"] == "a1"
    assert payload["user_id"] == "carol"
    assert payload["extra"]["reason"] == "json shape check"
