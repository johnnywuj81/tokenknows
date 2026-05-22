"""Quota 记账 + throttle (v0.4.4 T44 · 体验要素 #32).

覆盖:
- record_token_usage: 累加 + 月配额到顶自动 throttled
- is_quota_throttled 状态查询
- get_quota_usage_ratio 计算
- update_quota_limit: Owner 调上限 + 解除 throttle
- HTTP: GET /quota (status: healthy/warning/throttled)
- HTTP: PATCH /quota (上限调整 + 紧急放行)
- 评估器集成: throttled 项目跳过 cron / event / threshold 触发
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.auto_trigger import EventMatch, ThresholdSpec, TriggerSignal
from app.services import auto_trigger_service as svc
from app.services.auto_trigger.evaluator.event_evaluator import (
    GitHubEvent, evaluate_github_event,
)
from app.services.auto_trigger.evaluator.rule_evaluator import evaluate_cron_rules
from app.services.auto_trigger.evaluator.threshold_evaluator import (
    evaluate_threshold_rules,
)


# ─── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.services import generation_service
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    monkeypatch.setattr(generation_service, "_assets", {})
    monkeypatch.setattr(generation_service, "_chapters", {})
    return s


@pytest.fixture
def client(fresh_db):
    return TestClient(app)


# ─── service: record_token_usage ──────────────────────────


def test_record_token_usage_accumulates(fresh_db):
    q1 = svc.record_token_usage("proj-1", 1000)
    assert q1.tokens_used == 1000
    assert q1.auto_gen_count == 1
    assert q1.is_throttled is False

    q2 = svc.record_token_usage("proj-1", 2500)
    assert q2.tokens_used == 3500
    assert q2.auto_gen_count == 2


def test_record_token_usage_throttles_when_exhausted(fresh_db):
    # 默认 limit 5M; 一次性记 6M 触发 throttle
    q = svc.record_token_usage("proj-1", 6_000_000)
    assert q.is_throttled is True
    assert q.throttled_at is not None


def test_record_token_usage_below_limit_not_throttled(fresh_db):
    q = svc.record_token_usage("proj-1", 1_000_000)
    assert q.is_throttled is False


# ─── service: query ──────────────────────────────────────


def test_is_quota_throttled_false_initially(fresh_db):
    assert svc.is_quota_throttled("proj-1") is False


def test_is_quota_throttled_after_exhaust(fresh_db):
    svc.record_token_usage("proj-1", 6_000_000)
    assert svc.is_quota_throttled("proj-1") is True


def test_usage_ratio(fresh_db):
    svc.record_token_usage("proj-1", 1_000_000)
    ratio = svc.get_quota_usage_ratio("proj-1")
    assert 0.19 < ratio < 0.21  # ~20%


# ─── service: update_quota_limit ─────────────────────────


def test_update_quota_limit_raises(fresh_db):
    svc.record_token_usage("proj-1", 100)
    q = svc.update_quota_limit("proj-1", monthly_token_limit=10_000_000)
    assert q.monthly_token_limit == 10_000_000


def test_update_quota_unthrottle(fresh_db):
    svc.record_token_usage("proj-1", 6_000_000)
    assert svc.is_quota_throttled("proj-1")
    svc.update_quota_limit("proj-1", is_throttled=False)
    assert not svc.is_quota_throttled("proj-1")


def test_update_quota_negative_rejected(fresh_db):
    with pytest.raises(ValueError):
        svc.update_quota_limit("proj-1", monthly_token_limit=-1)


# ─── HTTP ────────────────────────────────────────────────


def test_get_quota_default_healthy(client):
    res = client.get("/api/v1/projects/proj-1/auto-triggers/quota")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "healthy"
    assert body["tokens_used"] == 0
    assert body["usage_ratio"] == 0.0


def test_get_quota_warning_status(client, fresh_db):
    svc.record_token_usage("proj-1", 4_500_000)  # 90%
    res = client.get("/api/v1/projects/proj-1/auto-triggers/quota")
    assert res.json()["status"] == "warning"


def test_get_quota_throttled_status(client, fresh_db):
    svc.record_token_usage("proj-1", 6_000_000)
    res = client.get("/api/v1/projects/proj-1/auto-triggers/quota")
    assert res.json()["status"] == "throttled"
    assert res.json()["is_throttled"] is True


def test_patch_quota_raises_limit(client):
    res = client.patch(
        "/api/v1/projects/proj-1/auto-triggers/quota",
        json={"monthly_token_limit": 10_000_000},
    )
    assert res.status_code == 200
    assert res.json()["monthly_token_limit"] == 10_000_000


def test_patch_quota_unthrottle(client, fresh_db):
    svc.record_token_usage("proj-1", 6_000_000)
    res = client.patch(
        "/api/v1/projects/proj-1/auto-triggers/quota",
        json={"is_throttled": False},
    )
    assert res.json()["is_throttled"] is False


def test_patch_quota_negative_400(client):
    res = client.patch(
        "/api/v1/projects/proj-1/auto-triggers/quota",
        json={"monthly_token_limit": -1},
    )
    assert res.status_code == 400


# ─── 评估器 throttle 集成 ────────────────────────────────


def test_cron_evaluator_skips_throttled_project(fresh_db):
    # 周一 09:00:30 (UTC) Mon
    MON = datetime(2026, 5, 18, 9, 0, 30, tzinfo=timezone.utc)
    svc.create_rule(
        project_id="proj-1", name="weekly", mode="cron",
        asset_type="weekly_report", cron_expr="0 9 * * 1",
        created_by="system",
    )
    # throttle proj-1
    svc.record_token_usage("proj-1", 6_000_000)
    stats = evaluate_cron_rules(now=MON)
    assert stats["scheduled"] == 0
    assert stats.get("skipped_quota", 0) == 1


def test_event_evaluator_skips_throttled_project(fresh_db):
    svc.create_rule(
        project_id="proj-1", name="adr", mode="event",
        asset_type="adr",
        event_match=EventMatch(
            event_type="github_pr_merged",
            label_any=["architecture-decision"],
        ),
        created_by="system",
    )
    svc.record_token_usage("proj-1", 6_000_000)
    ev = GitHubEvent(
        event_type="github_pr_merged", repo="x/y", number=1,
        labels=["architecture-decision"], title="x",
    )
    stats = evaluate_github_event(ev, "proj-1")
    assert stats["scheduled"] == 0
    assert stats.get("skipped_quota", 0) == 1


def test_threshold_evaluator_skips_throttled_project(fresh_db):
    from uuid import uuid4
    from app.schemas.asset import Asset, Chapter
    from app.services import generation_service

    # 在 proj-1 准备 50 章 approved + events 让 active project resolve
    asset_id = f"asset-{uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    a = Asset(
        id=asset_id, project_id="proj-1", type="weekly_report",
        title="x", status="draft", current_version=1,
        template_id="tpl-x", created_by="test",
        created_at=now, updated_at=now,
    )
    generation_service._assets[asset_id] = a
    generation_service._chapters[asset_id] = [
        Chapter(
            id=f"c{i}", asset_id=asset_id, order_index=i,
            title=f"§{i}", content="x", approval_state="approved",
        )
        for i in range(50)
    ]
    fresh_db.upsert_event(
        event_id="e1", project_id="proj-1", source_type="github",
        event_type="commit", occurred_at=now.isoformat(),
        ingested_at=now.isoformat(),
        content_hash="h1", json_str="{}",
    )
    svc.create_rule(
        project_id=None, name="book-rule", mode="threshold",
        asset_type="book",
        threshold_spec=ThresholdSpec(
            metric="approved_chapters_total", comparator=">=", value=50,
        ),
        created_by="system",
    )
    svc.record_token_usage("proj-1", 6_000_000)
    stats = evaluate_threshold_rules()
    assert stats["scheduled"] == 0
    assert stats.get("skipped_quota", 0) == 1


# ─── Dispatcher 记账集成 ─────────────────────────────────


@pytest.mark.asyncio
async def test_dispatcher_records_tokens_after_fire(fresh_db, monkeypatch):
    """dispatcher.fire 成功后, quota.tokens_used 增加估算值."""
    from datetime import timedelta
    import json
    from unittest.mock import AsyncMock
    from app.schemas.asset import Asset
    from app.services import generation_service
    from app.services.auto_trigger import dispatcher
    from app.services.auto_trigger_service import _now, _to_iso

    # mock LLM
    async def _fake(project_id, req, user_id=None, trigger_meta=None):
        return Asset(
            id="asset-mock", project_id=project_id, type=req.type,
            title="x", status="draft", current_version=1,
            template_id=f"tpl-{req.type}", created_by=user_id or "?",
            trigger_meta=trigger_meta,
            created_at=_now(), updated_at=_now(),
        )
    monkeypatch.setattr(generation_service, "start_generation", AsyncMock(side_effect=_fake))

    rule = svc.create_rule(
        project_id="proj-1", name="weekly", mode="cron",
        asset_type="weekly_report", cron_expr="0 9 * * 1",
        created_by="system",
    )
    exe = svc.schedule_execution(
        rule, "proj-1", TriggerSignal(type="cron", summary="x"),
        withdraw_window_min=0,
    )
    # fire_at 提前
    raw = exe.model_dump()
    raw["fire_at"] = _to_iso(_now() - timedelta(seconds=1))
    fresh_db.update_trigger_execution(
        execution_id=exe.id, status=exe.status,
        fired_at=None, asset_id=None,
        json_str=json.dumps(raw, default=str),
    )

    assert svc.get_quota_usage_ratio("proj-1") == 0.0
    artifact = await dispatcher.fire(exe.id)
    assert artifact is not None

    # weekly_report 估 5000 tokens
    q = svc.get_or_create_quota("proj-1")
    assert q.tokens_used == 5000
    assert q.auto_gen_count == 1
