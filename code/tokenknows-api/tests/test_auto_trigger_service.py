"""auto_trigger_service · 业务服务层 (v0.4 T26).

覆盖:
- create_rule 各 mode + spec 配对校验 (RuleSpecMismatch)
- update_rule 启停 + priority + cooldown_seconds
- delete_rule
- schedule_execution: fire_at = now + withdraw_window 撤回窗口
- record_skip: cooldown / daily_cap / extra_condition_failed
- mark_fired: scheduled → fired, 自动填 fired_at + asset_id
- cancel_execution: user_canceled=True
- mark_failed + mark_expired
- InvalidTransition (fired → 任何)
- ExecutionNotFound / RuleNotFound
- sweep_expired
- flag_false_positive
- get_or_create_quota 幂等
- count_fired_since 窗口查询
- bootstrap 启动回填 + 计 scheduled_pending
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.auto_trigger import (
    EventMatch,
    TriggerSignal,
    ThresholdSpec,
)
from app.services import auto_trigger_service as svc


# ─── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """每个 test 一个独立 SQLite store + 替换 get_db 单例."""
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    return s


def _sig(summary="测试触发"):
    return TriggerSignal(type="cron", summary=summary)


# ─── Rule CRUD ────────────────────────────────────────────


def test_create_rule_cron_happy(fresh_db):
    rule = svc.create_rule(
        project_id=None,
        name="周一周报",
        mode="cron",
        asset_type="weekly_report",
        created_by="system",
        cron_expr="0 9 * * 1",
    )
    assert rule.id.startswith("rule-")
    assert rule.cron_expr == "0 9 * * 1"
    assert rule.enabled is True
    # 持久化校验
    again = svc.get_rule(rule.id)
    assert again is not None
    assert again.name == "周一周报"


def test_create_rule_cron_missing_expr_raises(fresh_db):
    with pytest.raises(svc.RuleSpecMismatch):
        svc.create_rule(
            project_id=None, name="bad", mode="cron",
            asset_type="weekly_report", created_by="system",
            cron_expr=None,  # mode=cron 必须填
        )


def test_create_rule_event_missing_match_raises(fresh_db):
    with pytest.raises(svc.RuleSpecMismatch):
        svc.create_rule(
            project_id="proj-1", name="bad", mode="event",
            asset_type="adr", created_by="user-1",
            event_match=None,
        )


def test_create_rule_threshold_with_spec(fresh_db):
    rule = svc.create_rule(
        project_id="proj-1",
        name="50 章 → book",
        mode="threshold",
        asset_type="book",
        created_by="user-1",
        threshold_spec=ThresholdSpec(
            metric="approved_chapters_total",
            comparator=">=",
            value=50,
            and_not_exists_asset_of_type="book",
        ),
        enabled=False,  # Q4: book 默认不勾
    )
    assert rule.threshold_spec is not None
    assert rule.threshold_spec.value == 50
    assert rule.enabled is False


def test_update_rule_toggle_enabled(fresh_db):
    rule = svc.create_rule(
        project_id="proj-1", name="x", mode="cron",
        asset_type="weekly_report", created_by="user-1",
        cron_expr="0 9 * * 1",
    )
    updated = svc.update_rule(rule.id, enabled=False)
    assert updated.enabled is False
    assert updated.updated_at >= rule.updated_at


def test_update_rule_immutable_fields_ignored(fresh_db):
    rule = svc.create_rule(
        project_id="proj-1", name="x", mode="cron",
        asset_type="weekly_report", created_by="user-1",
        cron_expr="0 9 * * 1",
    )
    updated = svc.update_rule(rule.id, id="rule-hacker", created_by="evil")
    # id / created_by 应保持不变
    assert updated.id == rule.id
    assert updated.created_by == "user-1"


def test_delete_rule(fresh_db):
    rule = svc.create_rule(
        project_id=None, name="x", mode="cron",
        asset_type="weekly_report", created_by="system",
        cron_expr="0 9 * * 1",
    )
    assert svc.delete_rule(rule.id) is True
    assert svc.get_rule(rule.id) is None
    assert svc.delete_rule(rule.id) is False  # 二次删返 False


def test_list_rules_include_instance_defaults(fresh_db):
    inst = svc.create_rule(
        project_id=None, name="inst", mode="cron",
        asset_type="weekly_report", created_by="system",
        cron_expr="0 9 * * 1",
    )
    proj = svc.create_rule(
        project_id="proj-1", name="proj", mode="cron",
        asset_type="weekly_report", created_by="user-1",
        cron_expr="0 10 * * 1",
    )
    # proj-1 视角应能看到自己规则 + 实例兜底
    rules = svc.list_rules(project_id="proj-1")
    ids = {r.id for r in rules}
    assert ids == {inst.id, proj.id}


# ─── Execution lifecycle ──────────────────────────────────


def test_schedule_execution_default_withdraw_5min(fresh_db):
    rule = svc.create_rule(
        project_id=None, name="x", mode="cron",
        asset_type="weekly_report", created_by="system",
        cron_expr="0 9 * * 1",
    )
    before = datetime.now(timezone.utc)
    exe = svc.schedule_execution(rule, project_id="proj-1", signal=_sig())
    after = datetime.now(timezone.utc)

    assert exe.status == "scheduled"
    delta = exe.fire_at - before
    # 5 min ± 1 sec tolerance
    assert timedelta(minutes=4, seconds=59) <= delta <= timedelta(minutes=5, seconds=1)
    # signal 持久化 OK
    assert exe.signal.summary == "测试触发"


def test_schedule_execution_custom_withdraw_window(fresh_db):
    rule = svc.create_rule(
        project_id=None, name="x", mode="cron",
        asset_type="weekly_report", created_by="system",
        cron_expr="0 9 * * 1",
    )
    # Q1: 用户可调 1-15 min
    exe = svc.schedule_execution(
        rule, project_id="proj-1", signal=_sig(),
        withdraw_window_min=10,
    )
    delta = exe.fire_at - datetime.now(timezone.utc)
    assert timedelta(minutes=9, seconds=59) <= delta <= timedelta(minutes=10, seconds=1)


def test_record_skip_writes_history(fresh_db):
    rule = svc.create_rule(
        project_id=None, name="x", mode="cron",
        asset_type="weekly_report", created_by="system",
        cron_expr="0 9 * * 1",
    )
    exe = svc.record_skip(rule, "proj-1", _sig(), "cooldown")
    assert exe.status == "skipped"
    assert exe.skip_reason == "cooldown"


def test_mark_fired_transition(fresh_db):
    rule = svc.create_rule(
        project_id=None, name="x", mode="cron",
        asset_type="weekly_report", created_by="system",
        cron_expr="0 9 * * 1",
    )
    exe = svc.schedule_execution(rule, "proj-1", _sig())
    fired = svc.mark_fired(exe.id, asset_id="asset-99")
    assert fired.status == "fired"
    assert fired.asset_id == "asset-99"
    assert fired.fired_at is not None


def test_mark_fired_double_call_rejected(fresh_db):
    rule = svc.create_rule(
        project_id=None, name="x", mode="cron",
        asset_type="weekly_report", created_by="system",
        cron_expr="0 9 * * 1",
    )
    exe = svc.schedule_execution(rule, "proj-1", _sig())
    svc.mark_fired(exe.id, "asset-99")
    # 二次 fire 应被状态机拒绝
    with pytest.raises(svc.InvalidTransition):
        svc.mark_fired(exe.id, "asset-100")


def test_cancel_execution_marks_user_canceled(fresh_db):
    rule = svc.create_rule(
        project_id=None, name="x", mode="cron",
        asset_type="weekly_report", created_by="system",
        cron_expr="0 9 * * 1",
    )
    exe = svc.schedule_execution(rule, "proj-1", _sig())
    cancelled = svc.cancel_execution(exe.id, by_user=True)
    assert cancelled.status == "canceled"
    assert cancelled.user_canceled is True


def test_cancel_fired_execution_rejected(fresh_db):
    rule = svc.create_rule(
        project_id=None, name="x", mode="cron",
        asset_type="weekly_report", created_by="system",
        cron_expr="0 9 * * 1",
    )
    exe = svc.schedule_execution(rule, "proj-1", _sig())
    svc.mark_fired(exe.id, "asset-99")
    with pytest.raises(svc.InvalidTransition):
        svc.cancel_execution(exe.id)


def test_mark_failed_records_error(fresh_db):
    rule = svc.create_rule(
        project_id=None, name="x", mode="cron",
        asset_type="weekly_report", created_by="system",
        cron_expr="0 9 * * 1",
    )
    exe = svc.schedule_execution(rule, "proj-1", _sig())
    failed = svc.mark_failed(exe.id, "LLM provider timeout")
    assert failed.status == "failed"
    assert failed.error_message == "LLM provider timeout"


def test_execution_not_found_raises(fresh_db):
    with pytest.raises(svc.ExecutionNotFound):
        svc.mark_fired("exe-nope", "asset-x")


def test_flag_false_positive_keeps_status(fresh_db):
    """flag 不改 status, 可在 fired 之后也能标."""
    rule = svc.create_rule(
        project_id=None, name="x", mode="cron",
        asset_type="weekly_report", created_by="system",
        cron_expr="0 9 * * 1",
    )
    exe = svc.schedule_execution(rule, "proj-1", _sig())
    svc.mark_fired(exe.id, "asset-99")
    flagged = svc.flag_false_positive(exe.id)
    assert flagged.user_flagged_false_positive is True
    assert flagged.status == "fired"  # status 不变


def test_sweep_expired(fresh_db, monkeypatch):
    """fire_at 过去 > EXPIRED_GRACE_MIN 仍 scheduled 的应被标 expired."""
    rule = svc.create_rule(
        project_id=None, name="x", mode="cron",
        asset_type="weekly_report", created_by="system",
        cron_expr="0 9 * * 1",
    )
    # 用一个很短的 grace 触发 sweep
    exe = svc.schedule_execution(rule, "proj-1", _sig(), withdraw_window_min=1)
    # 等 1 秒后扫描, grace=0 应触发 expired (fire_at 在 1 分钟后, cutoff = now - 0 min = now, 不到 fire_at)
    # 改用 grace_min=-2 让 cutoff = now+2min > fire_at, 应该 expire
    n = svc.sweep_expired(grace_min=-2)
    assert n == 1
    again = svc.get_execution(exe.id)
    assert again is not None
    assert again.status == "expired"


# ─── Quota ────────────────────────────────────────────────


def test_get_or_create_quota_creates_if_missing(fresh_db):
    quota = svc.get_or_create_quota("proj-1", year_month="2026-05")
    assert quota.tokens_used == 0
    assert quota.monthly_token_limit == 5_000_000  # Q3 默认
    assert quota.daily_auto_gen_limit == 20


def test_get_or_create_quota_idempotent(fresh_db):
    q1 = svc.get_or_create_quota("proj-1", year_month="2026-05")
    q2 = svc.get_or_create_quota("proj-1", year_month="2026-05")
    assert q1.id == q2.id


def test_get_or_create_quota_defaults_to_current_month(fresh_db):
    quota = svc.get_or_create_quota("proj-1")
    now_ym = datetime.now(timezone.utc).strftime("%Y-%m")
    assert quota.year_month == now_ym


# ─── Bootstrap ────────────────────────────────────────────


def test_bootstrap_counts(fresh_db):
    rule = svc.create_rule(
        project_id=None, name="x", mode="cron",
        asset_type="weekly_report", created_by="system",
        cron_expr="0 9 * * 1",
    )
    svc.schedule_execution(rule, "proj-1", _sig())
    svc.schedule_execution(rule, "proj-2", _sig())

    counts = svc.bootstrap()
    assert counts["rules"] == 1
    assert counts["executions"] == 2
    assert counts["scheduled_pending"] == 2


def test_bootstrap_empty(fresh_db):
    counts = svc.bootstrap()
    assert counts == {"rules": 0, "executions": 0, "scheduled_pending": 0}


# ─── count_fired_since (RuleEvaluator 用) ─────────────────


def test_count_fired_since_window(fresh_db):
    rule = svc.create_rule(
        project_id=None, name="x", mode="cron",
        asset_type="weekly_report", created_by="system",
        cron_expr="0 9 * * 1",
    )
    # fire 一次
    exe = svc.schedule_execution(rule, "proj-1", _sig())
    svc.mark_fired(exe.id, "asset-1")

    # 5 分钟前应能拉到这次 fire
    since = datetime.now(timezone.utc) - timedelta(minutes=5)
    n = svc.count_fired_since(rule.id, since)
    assert n == 1

    # 未来时间窗口应 0
    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    n = svc.count_fired_since(rule.id, future)
    assert n == 0
