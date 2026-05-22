"""RuleEvaluator + CronMatcher + ConditionEvaluator (v0.4 T29).

覆盖:
- CronMatcher:
  * 周一 09:00 cron: 在窗口内 / 不在窗口
  * now 恰好等于 cron 时刻 (边界)
  * 非法 cron / is_valid_cron 边界
- ConditionEvaluator:
  * events_last_7d 通过 / 不通过 (6 种 comparator)
  * cond=None → 视为通过
  * 不支持 metric → 视为通过 + log warning
- RuleEvaluator:
  * 命中 cron 时间 → schedule_execution
  * 不到点 → 跳过整条
  * cooldown 内 → record_skip("cooldown")
  * daily_cap 达 → record_skip("daily_cap_reached")
  * extra_condition 不满足 → record_skip("extra_condition_failed")
  * 实例级规则 fan-out 到 events 表里的 active 项目
  * 项目级规则只触发自己
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from freezegun import freeze_time

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.auto_trigger import ExtraCondition
from app.services import auto_trigger_service as svc
from app.services.auto_trigger.evaluator import (
    SCAN_WINDOW_SECONDS,
    evaluate_cron_rules,
    evaluate_extra_condition,
    matches_in_window,
)
from app.services.auto_trigger.evaluator.cron_matcher import is_valid_cron


# ─── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    return s


def _insert_event(store: SqliteStore, project_id: str, occurred_at: datetime,
                   event_id: str | None = None):
    """插一条 event 给 ConditionEvaluator / fan-out 测试用."""
    eid = event_id or f"evt-{occurred_at.isoformat()}"
    store.upsert_event(
        event_id=eid,
        project_id=project_id,
        source_type="github",
        event_type="commit",
        occurred_at=occurred_at.isoformat(),
        ingested_at=occurred_at.isoformat(),
        content_hash=eid,  # 简化, 测试场景
        json_str=json.dumps({"id": eid}),
    )


# 一个固定的"周一 09:00:30" 时刻 (UTC)
MON_0900 = datetime(2026, 5, 18, 9, 0, 30, tzinfo=timezone.utc)


# ─── CronMatcher ──────────────────────────────────────────


def test_cron_matcher_within_window():
    """周一 09:00:30 时, '0 9 * * 1' (周一 9 点) 应在 60s 窗口内匹配."""
    assert matches_in_window("0 9 * * 1", MON_0900, 60) is True


def test_cron_matcher_outside_window():
    """周一 09:01:30 时, 距 09:00:00 = 90s > 60s 窗口, 不匹配."""
    later = datetime(2026, 5, 18, 9, 1, 30, tzinfo=timezone.utc)
    assert matches_in_window("0 9 * * 1", later, 60) is False


def test_cron_matcher_exact_cron_moment():
    """now 恰好等于 cron 时刻 (09:00:00) 时, 应匹配 (边界)."""
    exact = datetime(2026, 5, 18, 9, 0, 0, tzinfo=timezone.utc)
    assert matches_in_window("0 9 * * 1", exact, 60) is True


def test_cron_matcher_wrong_day():
    """周二 09:00:30 时, 周一 cron 不应匹配 (上一次到点是 24h 前)."""
    tue = datetime(2026, 5, 19, 9, 0, 30, tzinfo=timezone.utc)
    assert matches_in_window("0 9 * * 1", tue, 60) is False


def test_cron_matcher_empty_expr():
    assert matches_in_window("", MON_0900, 60) is False


def test_cron_matcher_invalid_expr():
    assert matches_in_window("not a cron", MON_0900, 60) is False


def test_is_valid_cron():
    assert is_valid_cron("0 9 * * 1") is True
    assert is_valid_cron("*/5 * * * *") is True
    assert is_valid_cron("invalid") is False
    assert is_valid_cron("") is False


# ─── ConditionEvaluator ───────────────────────────────────


def test_evaluate_condition_none_passes(fresh_db):
    passed, actual = evaluate_extra_condition(None, "proj-1", now=MON_0900)
    assert passed is True
    assert actual is None


def test_evaluate_condition_events_last_7d_passes(fresh_db):
    """30+ 个事件在 7d 内 → events_last_7d >= 30 满足."""
    for i in range(30):
        # i+1 小时前, 范围 1-30 小时, 都 < 2 天 (远在 7 天窗口内)
        _insert_event(fresh_db, "proj-1",
                      MON_0900 - timedelta(hours=i + 1),
                      event_id=f"evt-{i}")
    cond = ExtraCondition(metric="events_last_7d", comparator=">=", value=30)
    passed, actual = evaluate_extra_condition(cond, "proj-1", now=MON_0900)
    assert passed is True
    assert actual == 30


def test_evaluate_condition_events_last_7d_fails(fresh_db):
    """5 个事件, < 30 阈值."""
    for i in range(5):
        _insert_event(fresh_db, "proj-1", MON_0900 - timedelta(hours=i),
                      event_id=f"evt-{i}")
    cond = ExtraCondition(metric="events_last_7d", comparator=">=", value=30)
    passed, actual = evaluate_extra_condition(cond, "proj-1", now=MON_0900)
    assert passed is False
    assert actual == 5


def test_evaluate_condition_old_events_excluded(fresh_db):
    """8 天前的事件不计入 events_last_7d."""
    _insert_event(fresh_db, "proj-1", MON_0900 - timedelta(days=8),
                  event_id="old")
    _insert_event(fresh_db, "proj-1", MON_0900 - timedelta(days=2),
                  event_id="recent")
    cond = ExtraCondition(metric="events_last_7d", comparator=">=", value=2)
    passed, actual = evaluate_extra_condition(cond, "proj-1", now=MON_0900)
    assert passed is False  # 只有 1 个在窗口内
    assert actual == 1


def test_evaluate_condition_unsupported_metric_passes(fresh_db):
    """不支持的 metric 视为通过 (不阻塞触发); 由 caller log."""
    cond = ExtraCondition(metric="future_metric_v2", comparator=">=", value=10)
    passed, actual = evaluate_extra_condition(cond, "proj-1", now=MON_0900)
    assert passed is True
    assert actual is None


def test_evaluate_condition_all_comparators(fresh_db):
    """6 种 comparator 都能工作."""
    for i in range(10):
        _insert_event(fresh_db, "proj-1", MON_0900 - timedelta(hours=i),
                      event_id=f"e{i}")
    # 实际 10 个事件
    cases = [
        (">=", 10, True),
        (">=", 11, False),
        ("<=", 10, True),
        ("<=", 9, False),
        ("==", 10, True),
        ("==", 11, False),
        ("!=", 10, False),
        ("!=", 11, True),
        (">", 9, True),
        (">", 10, False),
        ("<", 11, True),
        ("<", 10, False),
    ]
    for comp, val, expected in cases:
        cond = ExtraCondition(metric="events_last_7d", comparator=comp, value=val)
        passed, _ = evaluate_extra_condition(cond, "proj-1", now=MON_0900)
        assert passed is expected, f"{comp} {val} -> expected {expected}"


# ─── RuleEvaluator 主流程 ────────────────────────────────


def _create_weekly_rule(project_id: str | None = None, **overrides):
    """复用: 创建一个周一 09:00 的 cron 规则."""
    defaults = {
        "project_id": project_id,
        "name": f"周报-{project_id or 'instance'}",
        "mode": "cron",
        "asset_type": "weekly_report",
        "cron_expr": "0 9 * * 1",
        "created_by": "system",
        "cooldown_seconds": 3600,
        "daily_cap": 5,
    }
    defaults.update(overrides)
    return svc.create_rule(**defaults)


def test_evaluator_matched_schedules_execution(fresh_db):
    """周一 09:00:30 + 项目级 cron rule → schedule_execution."""
    rule = _create_weekly_rule(project_id="proj-1")
    stats = evaluate_cron_rules(now=MON_0900)
    assert stats["matched"] == 1
    assert stats["scheduled"] == 1
    execs = svc.list_executions(rule_id=rule.id)
    assert len(execs) == 1
    assert execs[0].status == "scheduled"


def test_evaluator_not_match_when_off_time(fresh_db):
    """周二 09:00 时, 周一 cron 不匹配."""
    _create_weekly_rule(project_id="proj-1")
    tue = datetime(2026, 5, 19, 9, 0, 30, tzinfo=timezone.utc)
    stats = evaluate_cron_rules(now=tue)
    assert stats["matched"] == 0
    assert stats["scheduled"] == 0


def test_evaluator_skipped_cooldown(fresh_db):
    """已 fired 过且在 cooldown 内 → record_skip(cooldown)."""
    rule = _create_weekly_rule(project_id="proj-1", cooldown_seconds=3600)
    # 模拟上次 fired
    exe = svc.schedule_execution(rule, "proj-1",
        svc.TriggerSignal(type="manual", summary="pre"))
    svc.mark_fired(exe.id, "asset-prior")
    # 评估时仍在 1 小时内
    stats = evaluate_cron_rules(now=MON_0900)
    assert stats["skipped_cooldown"] == 1
    assert stats["scheduled"] == 0
    # 应该有 2 条 execution: 旧 fired + 新 skipped
    execs = svc.list_executions(rule_id=rule.id)
    assert len(execs) == 2
    assert any(e.skip_reason == "cooldown" for e in execs)


def test_evaluator_skipped_daily_cap(fresh_db):
    """当日 fired 达 daily_cap → record_skip(daily_cap_reached).

    用 freeze_time 让 fired_at 落在 08:00 (cooldown 已过), evaluate at 09:00:30
    (cron 仍匹配 60s 窗口, daily_cap 达上限).
    """
    rule = _create_weekly_rule(project_id="proj-1",
                                 cooldown_seconds=60,  # 60s cooldown
                                 daily_cap=1)
    # 当日 08:00 已 fired 一次
    with freeze_time("2026-05-18 08:00:00+00:00"):
        exe = svc.schedule_execution(rule, "proj-1",
            svc.TriggerSignal(type="manual", summary="pre"))
        svc.mark_fired(exe.id, "asset-prior")
    # 09:00:30 评估: cooldown 已过 (距 fired 1 小时), 但 daily_cap=1 达上限
    stats = evaluate_cron_rules(now=MON_0900)
    assert stats["skipped_daily_cap"] == 1
    assert stats["skipped_cooldown"] == 0
    assert stats["scheduled"] == 0


def test_evaluator_skipped_extra_condition(fresh_db):
    """events_last_7d < 30 时 → record_skip(extra_condition_failed)."""
    rule = _create_weekly_rule(
        project_id="proj-1",
        extra_condition=ExtraCondition(
            metric="events_last_7d", comparator=">=", value=30
        ),
    )
    # 只有 5 个事件 < 30 (都在 7 天内)
    for i in range(5):
        _insert_event(fresh_db, "proj-1", MON_0900 - timedelta(hours=i + 1),
                      event_id=f"e{i}")
    stats = evaluate_cron_rules(now=MON_0900)
    assert stats["skipped_extra_condition"] == 1
    assert stats["scheduled"] == 0


def test_evaluator_passes_extra_condition(fresh_db):
    """events_last_7d ≥ 30 时 → 正常 schedule."""
    rule = _create_weekly_rule(
        project_id="proj-1",
        extra_condition=ExtraCondition(
            metric="events_last_7d", comparator=">=", value=30
        ),
    )
    for i in range(35):
        # 1-35 小时前, 都在 7 天内
        _insert_event(fresh_db, "proj-1", MON_0900 - timedelta(hours=i + 1),
                      event_id=f"e{i}")
    stats = evaluate_cron_rules(now=MON_0900)
    assert stats["scheduled"] == 1


def test_evaluator_instance_rule_fans_out(fresh_db):
    """实例级规则 (project_id=None) 应 fan-out 到所有有 events 的项目."""
    _create_weekly_rule(project_id=None)
    # 3 个项目都有事件
    for pid in ("proj-A", "proj-B", "proj-C"):
        _insert_event(fresh_db, pid, MON_0900 - timedelta(days=1),
                      event_id=f"e-{pid}")
    stats = evaluate_cron_rules(now=MON_0900)
    assert stats["matched"] == 1  # 1 条 cron 命中
    assert stats["scheduled"] == 3  # fan-out 到 3 个项目


def test_evaluator_project_rule_isolates(fresh_db):
    """项目级规则只对自己 project 触发, 其他项目有 events 也不会被波及."""
    _create_weekly_rule(project_id="proj-A")
    for pid in ("proj-A", "proj-B"):
        _insert_event(fresh_db, pid, MON_0900 - timedelta(days=1),
                      event_id=f"e-{pid}")
    stats = evaluate_cron_rules(now=MON_0900)
    assert stats["scheduled"] == 1


def test_evaluator_disabled_rule_ignored(fresh_db):
    """enabled=False 的规则不进 evaluator 候选."""
    _create_weekly_rule(project_id="proj-1", enabled=False)
    stats = evaluate_cron_rules(now=MON_0900)
    assert stats["evaluated"] == 0
    assert stats["scheduled"] == 0


def test_evaluator_non_cron_mode_ignored(fresh_db):
    """mode=event/threshold 的规则不进 cron_evaluator (list_all_rules query 已过滤)."""
    from app.schemas.auto_trigger import EventMatch, ThresholdSpec
    # 1 条 event + 1 条 threshold + 1 条 cron, 期望只评估 cron 那条
    svc.create_rule(
        project_id="proj-1", name="event-rule", mode="event", asset_type="adr",
        event_match=EventMatch(event_type="github_pr_merged"),
        created_by="system",
    )
    svc.create_rule(
        project_id="proj-1", name="threshold-rule", mode="threshold", asset_type="book",
        threshold_spec=ThresholdSpec(
            metric="approved_chapters_total", comparator=">=", value=50,
        ),
        enabled=False, cooldown_seconds=604800,
        created_by="system",
    )
    _create_weekly_rule(project_id="proj-1")
    stats = evaluate_cron_rules(now=MON_0900)
    assert stats["evaluated"] == 1  # 只 1 条 cron
    assert stats["scheduled"] == 1


# ─── 集成: scan window 配置正确 ──────────────────────────


def test_scan_window_constant():
    assert SCAN_WINDOW_SECONDS == 60
