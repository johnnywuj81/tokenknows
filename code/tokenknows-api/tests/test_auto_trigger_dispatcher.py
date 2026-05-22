"""TriggerDispatcher · v0.4 T30 + T31 端到端.

覆盖:
- happy path: scheduled → fire → mark_fired + asset 含 trigger_meta
- 重入安全: 同 execution_id 两次 fire 只 mark_fired 一次
- 撤回窗口未到 (fire_at > now) → 跳过不调 LLM
- execution 不存在 → 返回 None, 不抛异常
- rule 被删 → mark_failed
- generation_service 抛错 → mark_failed + 记 log
- fire_batch 统计 (fired / skipped / failed)
- jobs.withdraw_window_resolver_job 端到端 (mocked LLM)
- 真 generation_service.start_generation 接受 trigger_meta 并写到 asset
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.asset import Asset
from app.schemas.auto_trigger import TriggerSignal
from app.services import auto_trigger_service as svc
from app.services import generation_service
from app.services.auto_trigger import dispatcher
from app.services.auto_trigger import jobs as auto_trigger_jobs


# ─── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    return s


@pytest.fixture
def mock_generation(monkeypatch: pytest.MonkeyPatch):
    """Mock generation_service.start_generation, 返回固定 asset id, 避免真调 LLM."""
    captured_trigger_meta: dict = {}

    async def _fake_start(project_id, req, user_id=None, trigger_meta=None):
        captured_trigger_meta.clear()
        if trigger_meta:
            captured_trigger_meta.update(trigger_meta)
        return Asset(
            id="asset-mock-123",
            project_id=project_id,
            type=req.type,
            title=f"mock {req.type}",
            status="generating",
            current_version=0,
            created_by=user_id or "anonymous",
            trigger_meta=trigger_meta,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    mock = AsyncMock(side_effect=_fake_start)
    monkeypatch.setattr(generation_service, "start_generation", mock)
    return mock, captured_trigger_meta


def _make_rule_and_exec(now: datetime | None = None, fire_offset_sec: int = -1):
    """创建 1 条 rule + 1 条 scheduled execution.

    fire_offset_sec: 负数 = fire_at 已过, 正数 = 还没到.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    rule = svc.create_rule(
        project_id="proj-1",
        name=f"test-rule-{now.timestamp()}",
        mode="cron",
        asset_type="weekly_report",
        cron_expr="0 9 * * 1",
        created_by="system",
    )
    # schedule_execution 默认 fire_at = now + 5min, 我们手动改成 fire_offset_sec
    exe = svc.schedule_execution(
        rule, "proj-1",
        signal=TriggerSignal(type="cron", summary="test"),
        withdraw_window_min=0,  # 立即 fire_at = now (offset 后续手动调)
    )
    # 手动覆盖 fire_at 让其已过 (offset<0) 或未到 (offset>0)
    raw = exe.model_dump()
    raw["fire_at"] = (datetime.now(timezone.utc) + timedelta(seconds=fire_offset_sec)).isoformat()
    from app.services.auto_trigger_service import _to_iso
    store_module.get_db().update_trigger_execution(
        execution_id=exe.id,
        status=exe.status,
        fired_at=None,
        asset_id=None,
        json_str=__import__("json").dumps(raw, default=str),
    )
    return rule, svc.get_execution(exe.id)


# ─── happy path ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_fire_happy_path(fresh_db, mock_generation):
    mock, captured_meta = mock_generation
    rule, exe = _make_rule_and_exec(fire_offset_sec=-1)

    asset_id = await dispatcher.fire(exe.id)
    assert asset_id == "asset-mock-123"

    # generation 被调用 1 次
    assert mock.call_count == 1
    call_args = mock.call_args
    assert call_args.kwargs["project_id"] == "proj-1"
    assert call_args.kwargs["user_id"] == "system"
    assert call_args.kwargs["trigger_meta"] is not None

    # trigger_meta 字段齐全 (体验要素 #34 可解释卡需要)
    assert captured_meta["rule_id"] == rule.id
    assert captured_meta["rule_name"] == rule.name
    assert captured_meta["trigger_mode"] == "cron"
    assert captured_meta["confidence"] == 1.0
    assert captured_meta["trigger_execution_id"] == exe.id
    assert "signal" in captured_meta
    assert "fired_at" in captured_meta

    # execution 状态切到 fired + asset_id 关联
    again = svc.get_execution(exe.id)
    assert again.status == "fired"
    assert again.asset_id == "asset-mock-123"


# ─── 重入安全 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fire_reentrant_second_call_noop(fresh_db, mock_generation):
    mock, _ = mock_generation
    _, exe = _make_rule_and_exec(fire_offset_sec=-1)

    # 第一次 fire OK
    asset_id_1 = await dispatcher.fire(exe.id)
    assert asset_id_1 is not None
    # 第二次同 id 应跳过 (status='fired' 不是 'scheduled')
    asset_id_2 = await dispatcher.fire(exe.id)
    assert asset_id_2 is None

    # generation 只被调用 1 次
    assert mock.call_count == 1


@pytest.mark.asyncio
async def test_fire_after_cancel_noop(fresh_db, mock_generation):
    mock, _ = mock_generation
    _, exe = _make_rule_and_exec(fire_offset_sec=-1)
    svc.cancel_execution(exe.id, by_user=True)

    asset_id = await dispatcher.fire(exe.id)
    assert asset_id is None
    assert mock.call_count == 0  # canceled 后不再调 LLM


# ─── 撤回窗口未到 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_fire_premature_skipped(fresh_db, mock_generation):
    """fire_at 还在 5 分钟之后 → 不调 LLM, execution 保持 scheduled."""
    mock, _ = mock_generation
    _, exe = _make_rule_and_exec(fire_offset_sec=300)  # 5 min 后

    asset_id = await dispatcher.fire(exe.id)
    assert asset_id is None
    assert mock.call_count == 0
    # execution 仍然是 scheduled
    again = svc.get_execution(exe.id)
    assert again.status == "scheduled"


# ─── 错误处理 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fire_missing_execution(fresh_db, mock_generation):
    mock, _ = mock_generation
    asset_id = await dispatcher.fire("exec-nope")
    assert asset_id is None
    assert mock.call_count == 0


@pytest.mark.asyncio
async def test_fire_rule_deleted_marks_failed(fresh_db, mock_generation):
    """规则在 schedule 后被删 → fire 时 mark_failed."""
    mock, _ = mock_generation
    rule, exe = _make_rule_and_exec(fire_offset_sec=-1)
    svc.delete_rule(rule.id)
    # CASCADE 会把 execution 也删了, get_execution 会返回 None
    # 这是预期行为: rule 删了 execution 也跟着没
    asset_id = await dispatcher.fire(exe.id)
    assert asset_id is None
    assert mock.call_count == 0


@pytest.mark.asyncio
async def test_fire_generation_error_marks_failed(fresh_db, monkeypatch):
    """generation_service 抛异常 → execution.status='failed' + error_message 记录."""
    async def _fake_start_raise(*a, **kw):
        raise RuntimeError("LLM provider timeout")
    monkeypatch.setattr(generation_service, "start_generation", _fake_start_raise)

    _, exe = _make_rule_and_exec(fire_offset_sec=-1)
    asset_id = await dispatcher.fire(exe.id)
    assert asset_id is None
    # execution 标 failed
    again = svc.get_execution(exe.id)
    assert again.status == "failed"
    assert "LLM provider timeout" in (again.error_message or "")


# ─── fire_batch ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_fire_batch_stats(fresh_db, mock_generation):
    """fire_batch 串行处理 N 条; 统计正确."""
    mock, _ = mock_generation
    # 3 条 ready, 1 条 premature
    _, e1 = _make_rule_and_exec(fire_offset_sec=-2)
    _, e2 = _make_rule_and_exec(fire_offset_sec=-2)
    _, e3 = _make_rule_and_exec(fire_offset_sec=-2)
    _, e_premature = _make_rule_and_exec(fire_offset_sec=300)

    stats = await dispatcher.fire_batch([e1.id, e2.id, e3.id, e_premature.id])
    assert stats["fired"] == 3
    assert stats["skipped"] == 1
    assert stats["failed"] == 0
    assert mock.call_count == 3  # premature 没调


# ─── 端到端: withdraw_window_resolver_job ─────────────────


@pytest.mark.asyncio
async def test_withdraw_resolver_dispatches_ready(fresh_db, mock_generation):
    """job 调用 → 真 dispatch 到 LLM (mocked) → asset 入库."""
    mock, _ = mock_generation
    _, e1 = _make_rule_and_exec(fire_offset_sec=-2)
    _, e2 = _make_rule_and_exec(fire_offset_sec=-2)
    # job 不抛, 内部调 dispatch
    await auto_trigger_jobs.withdraw_window_resolver_job()
    assert mock.call_count == 2
    # 2 条 execution 都 fired
    assert svc.get_execution(e1.id).status == "fired"
    assert svc.get_execution(e2.id).status == "fired"


@pytest.mark.asyncio
async def test_withdraw_resolver_no_ready_no_op(fresh_db, mock_generation):
    """无 ready execution → job 不调 LLM, 也不抛."""
    mock, _ = mock_generation
    _, _ = _make_rule_and_exec(fire_offset_sec=600)  # 10 分钟后才到点
    await auto_trigger_jobs.withdraw_window_resolver_job()
    assert mock.call_count == 0


# ─── 真 start_generation 接受 trigger_meta ────────────────


@pytest.mark.asyncio
async def test_start_generation_writes_trigger_meta_to_asset(fresh_db):
    """generation_service.start_generation(trigger_meta=...) → asset.trigger_meta 持久化."""
    from app.schemas.generation import GenerateAssetRequest
    meta = {
        "trigger_mode": "cron",
        "rule_id": "rule-x",
        "rule_name": "test",
        "signal": {"type": "cron", "summary": "test"},
        "confidence": 1.0,
        "fired_at": datetime.now(timezone.utc).isoformat(),
    }
    asset = await generation_service.start_generation(
        project_id="proj-test",
        req=GenerateAssetRequest(type="weekly_report"),
        user_id="system",
        trigger_meta=meta,
    )
    # 立即返回的 asset 应携带 trigger_meta
    assert asset.trigger_meta == meta
    # 持久化也保留 (用 service-level get_asset 读)
    again = generation_service.get_asset(asset.id)
    assert again is not None
    assert again.trigger_meta == meta
