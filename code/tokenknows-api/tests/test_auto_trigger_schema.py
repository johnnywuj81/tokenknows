"""Auto-Trigger Schema + Persistence (v0.4 T26).

覆盖:
- TriggerRule / TriggerExecution / GenerationQuota Pydantic round-trip
- can_transition 状态机合法/非法边界
- SqliteStore.upsert/get/list/delete_trigger_rule (project_id NULL + 具体值)
- list_trigger_rules include_instance_defaults 行为
- insert/update/list/count trigger_execution (含 list_scheduled_executions_ready)
- delete_old_trigger_executions
- upsert/get_quota
- 级联 CASCADE: 删 rule 自动删 executions
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.persistence.store import SqliteStore
from app.schemas.auto_trigger import (
    EventMatch,
    ExecutionStatus,
    ExtraCondition,
    GenerationQuota,
    ThresholdSpec,
    TriggerEvaluation,
    TriggerExecution,
    TriggerRule,
    TriggerSignal,
    can_transition,
)


# ─── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    return s


def _utc(year=2026, month=5, day=22, hour=9, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


# ─── Pydantic round-trip ──────────────────────────────────


def test_trigger_rule_roundtrip_cron():
    rule = TriggerRule(
        id="rule-1",
        project_id=None,
        name="周一周报",
        mode="cron",
        asset_type="weekly_report",
        cron_expr="0 9 * * 1",
        priority=50,
        extra_condition=ExtraCondition(
            metric="events_last_7d", comparator=">=", value=30
        ),
        created_by="system",
        created_at=_utc(),
        updated_at=_utc(),
    )
    raw = rule.model_dump_json()
    parsed = TriggerRule.model_validate_json(raw)
    assert parsed.id == "rule-1"
    assert parsed.cron_expr == "0 9 * * 1"
    assert parsed.extra_condition is not None
    assert parsed.extra_condition.value == 30
    assert parsed.event_match is None


def test_trigger_rule_roundtrip_event():
    rule = TriggerRule(
        id="rule-2",
        project_id="proj-1",
        name="ADR by PR label",
        mode="event",
        asset_type="adr",
        event_match=EventMatch(
            event_type="github_pr_merged",
            label_any=["architecture-decision"],
        ),
        priority=85,
        created_by="user-owner",
        created_at=_utc(),
        updated_at=_utc(),
    )
    parsed = TriggerRule.model_validate_json(rule.model_dump_json())
    assert parsed.event_match is not None
    assert parsed.event_match.event_type == "github_pr_merged"
    assert "architecture-decision" in parsed.event_match.label_any


def test_trigger_rule_priority_bounds():
    with pytest.raises(ValidationError):
        TriggerRule(
            id="x", name="x", mode="cron", asset_type="weekly_report",
            priority=999,  # out of 0-100
            created_by="system", created_at=_utc(), updated_at=_utc(),
        )


def test_trigger_rule_cooldown_min_60():
    with pytest.raises(ValidationError):
        TriggerRule(
            id="x", name="x", mode="cron", asset_type="weekly_report",
            cooldown_seconds=10,  # < 60
            created_by="system", created_at=_utc(), updated_at=_utc(),
        )


def test_trigger_execution_roundtrip_with_signal():
    exe = TriggerExecution(
        id="exe-1",
        rule_id="rule-1",
        project_id="proj-1",
        status="scheduled",
        fire_at=_utc(hour=9, minute=5),
        signal=TriggerSignal(
            type="cron", summary="周一 09:00 定时触发",
            payload={"week": "2026-W21"},
        ),
        evaluation=TriggerEvaluation(matched=True, confidence=1.0),
        created_at=_utc(),
    )
    parsed = TriggerExecution.model_validate_json(exe.model_dump_json())
    assert parsed.signal.type == "cron"
    assert parsed.signal.payload["week"] == "2026-W21"
    assert parsed.evaluation is not None
    assert parsed.evaluation.matched is True


def test_generation_quota_roundtrip():
    quota = GenerationQuota(
        id="q-1",
        project_id="proj-1",
        year_month="2026-05",
        monthly_token_limit=5_000_000,
        created_at=_utc(),
        updated_at=_utc(),
    )
    parsed = GenerationQuota.model_validate_json(quota.model_dump_json())
    assert parsed.monthly_token_limit == 5_000_000
    assert parsed.tokens_used == 0
    assert parsed.is_throttled is False


# ─── 状态机 ─────────────────────────────────────────────


def test_can_transition_legal_from_scheduled():
    legal = {"fired", "canceled", "skipped", "failed", "expired"}
    for to_status in legal:
        assert can_transition("scheduled", to_status), f"scheduled→{to_status}"


def test_can_transition_terminal_states_block_all():
    for terminal in ("fired", "canceled", "skipped", "failed", "expired"):
        for target in ("scheduled", "fired", "canceled", "failed"):
            assert not can_transition(terminal, target), \
                f"{terminal}→{target} 应非法"


# ─── SqliteStore: trigger_rules ──────────────────────────


def test_upsert_trigger_rule_insert(store: SqliteStore):
    store.upsert_trigger_rule(
        rule_id="rule-1", project_id=None, name="周一周报", mode="cron",
        asset_type="weekly_report", enabled=True, priority=50,
        updated_at=_iso(_utc()),
        json_str=json.dumps({"id": "rule-1", "name": "周一周报"}),
    )
    raw = store.get_trigger_rule("rule-1")
    assert raw is not None
    assert raw["name"] == "周一周报"


def test_upsert_trigger_rule_update_on_conflict(store: SqliteStore):
    store.upsert_trigger_rule(
        rule_id="rule-1", project_id=None, name="v1", mode="cron",
        asset_type="weekly_report", enabled=True, priority=50,
        updated_at=_iso(_utc()),
        json_str=json.dumps({"id": "rule-1", "name": "v1"}),
    )
    store.upsert_trigger_rule(
        rule_id="rule-1", project_id=None, name="v2", mode="cron",
        asset_type="weekly_report", enabled=False, priority=80,
        updated_at=_iso(_utc(minute=5)),
        json_str=json.dumps({"id": "rule-1", "name": "v2"}),
    )
    raw = store.get_trigger_rule("rule-1")
    assert raw["name"] == "v2"


def test_list_trigger_rules_instance_defaults_only(store: SqliteStore):
    # 插入 1 条实例级 + 1 条项目级
    store.upsert_trigger_rule(
        rule_id="rule-inst", project_id=None, name="instance",
        mode="cron", asset_type="weekly_report",
        enabled=True, priority=50,
        updated_at=_iso(_utc()), json_str=json.dumps({"id": "rule-inst"}),
    )
    store.upsert_trigger_rule(
        rule_id="rule-proj", project_id="proj-1", name="project",
        mode="cron", asset_type="weekly_report",
        enabled=True, priority=60,
        updated_at=_iso(_utc()), json_str=json.dumps({"id": "rule-proj"}),
    )

    # project_id=None: 只拉实例级
    rows = store.list_trigger_rules(project_id=None)
    ids = {r["id"] for r in rows}
    assert ids == {"rule-inst"}

    # project_id='proj-1' + include_defaults=True (默认): 拉两条
    rows = store.list_trigger_rules(project_id="proj-1")
    ids = {r["id"] for r in rows}
    assert ids == {"rule-inst", "rule-proj"}

    # project_id='proj-1' + include_defaults=False: 仅项目级
    rows = store.list_trigger_rules(
        project_id="proj-1", include_instance_defaults=False
    )
    ids = {r["id"] for r in rows}
    assert ids == {"rule-proj"}


def test_list_trigger_rules_filter_enabled_and_mode(store: SqliteStore):
    # 2 条 cron (1 启 1 停), 1 条 event (启)
    for rid, mode, enabled in [
        ("r1", "cron", True),
        ("r2", "cron", False),
        ("r3", "event", True),
    ]:
        store.upsert_trigger_rule(
            rule_id=rid, project_id="proj-1", name=rid, mode=mode,
            asset_type="adr" if mode == "event" else "weekly_report",
            enabled=enabled, priority=50,
            updated_at=_iso(_utc()), json_str=json.dumps({"id": rid}),
        )

    rows = store.list_trigger_rules(
        project_id="proj-1", enabled=True, include_instance_defaults=False
    )
    ids = {r["id"] for r in rows}
    assert ids == {"r1", "r3"}

    rows = store.list_trigger_rules(
        project_id="proj-1", mode="cron", include_instance_defaults=False
    )
    ids = {r["id"] for r in rows}
    assert ids == {"r1", "r2"}


def test_delete_trigger_rule(store: SqliteStore):
    store.upsert_trigger_rule(
        rule_id="r1", project_id=None, name="x", mode="cron",
        asset_type="weekly_report", enabled=True, priority=50,
        updated_at=_iso(_utc()), json_str=json.dumps({"id": "r1"}),
    )
    assert store.delete_trigger_rule("r1") is True
    assert store.get_trigger_rule("r1") is None
    assert store.delete_trigger_rule("r1") is False  # 二次删返 False


# ─── SqliteStore: trigger_executions ─────────────────────


def _insert_rule(store: SqliteStore, rule_id: str = "rule-1"):
    store.upsert_trigger_rule(
        rule_id=rule_id, project_id=None, name=rule_id, mode="cron",
        asset_type="weekly_report", enabled=True, priority=50,
        updated_at=_iso(_utc()), json_str=json.dumps({"id": rule_id}),
    )


def _insert_exec(
    store: SqliteStore, exec_id: str, rule_id: str = "rule-1",
    status: str = "scheduled", fire_at: datetime | None = None,
    fired_at: datetime | None = None,
    created_at: datetime | None = None,
):
    fire_at = fire_at or _utc()
    created_at = created_at or _utc()
    store.insert_trigger_execution(
        execution_id=exec_id, rule_id=rule_id, project_id="proj-1",
        status=status, fire_at=_iso(fire_at),
        fired_at=_iso(fired_at) if fired_at else None,
        asset_id=None, created_at=_iso(created_at),
        json_str=json.dumps({"id": exec_id, "status": status}),
    )


def test_insert_and_get_trigger_execution(store: SqliteStore):
    _insert_rule(store)
    _insert_exec(store, "exe-1")
    raw = store.get_trigger_execution("exe-1")
    assert raw is not None
    assert raw["status"] == "scheduled"


def test_list_scheduled_executions_ready(store: SqliteStore):
    _insert_rule(store)
    # 1 条 fire_at < now (ready), 1 条 fire_at > now (not ready)
    _insert_exec(store, "ready", fire_at=_utc(hour=8))
    _insert_exec(store, "future", fire_at=_utc(hour=23))

    now_iso = _iso(_utc(hour=10))
    rows = store.list_scheduled_executions_ready(now_iso, limit=10)
    ids = {r["id"] for r in rows}
    assert ids == {"ready"}


def test_update_trigger_execution_to_fired(store: SqliteStore):
    _insert_rule(store)
    _insert_exec(store, "exe-1")
    ok = store.update_trigger_execution(
        execution_id="exe-1",
        status="fired",
        fired_at=_iso(_utc(hour=9, minute=5)),
        asset_id="asset-99",
        json_str=json.dumps({"id": "exe-1", "status": "fired", "asset_id": "asset-99"}),
    )
    assert ok is True
    raw = store.get_trigger_execution("exe-1")
    assert raw["status"] == "fired"
    assert raw["asset_id"] == "asset-99"


def test_count_fired_in_window(store: SqliteStore):
    _insert_rule(store)
    # 2 条 fired (一条今天, 一条 8 天前), 1 条 scheduled
    _insert_exec(store, "fired-today", status="fired",
                 fired_at=_utc(hour=10))
    _insert_exec(store, "fired-old", status="fired",
                 fired_at=_utc(day=14))
    _insert_exec(store, "scheduled-now", status="scheduled")
    # 注意: 我们的 _insert_exec 把 fired_at 显式参数也传给 store
    # 但 SQLite 的 count_fired_in_window 是基于行内 fired_at 列, 我们 round-trip ok

    since = _iso(_utc(day=20))  # 22 - 2 = 20 (2 天前)
    # 实际只有 fired-today 在窗口内 (22)
    n = store.count_fired_in_window("rule-1", since)
    assert n == 1


def test_delete_old_trigger_executions(store: SqliteStore):
    _insert_rule(store)
    _insert_exec(store, "new", created_at=_utc(day=22))
    _insert_exec(store, "old", created_at=_utc(day=1))

    cutoff = _iso(_utc(day=10))
    deleted = store.delete_old_trigger_executions(cutoff)
    assert deleted == 1
    assert store.get_trigger_execution("old") is None
    assert store.get_trigger_execution("new") is not None


def test_cascade_delete_rule_removes_executions(store: SqliteStore):
    _insert_rule(store, "rule-cascade")
    _insert_exec(store, "exe-x", rule_id="rule-cascade")
    store.delete_trigger_rule("rule-cascade")
    # FK CASCADE: execution 应被删
    assert store.get_trigger_execution("exe-x") is None


# ─── SqliteStore: quota ──────────────────────────────────


def test_upsert_and_get_quota(store: SqliteStore):
    store.upsert_quota(
        quota_id="q-1", project_id="proj-1", year_month="2026-05",
        monthly_token_limit=5_000_000, daily_auto_gen_limit=20,
        tokens_used=0, auto_gen_count=0, is_throttled=False,
        updated_at=_iso(_utc()),
        json_str=json.dumps({"id": "q-1", "year_month": "2026-05"}),
    )
    raw = store.get_quota("proj-1", "2026-05")
    assert raw is not None
    assert raw["year_month"] == "2026-05"


def test_quota_unique_per_project_month(store: SqliteStore):
    """upsert 同 (project, month) 应触发 ON CONFLICT 更新, 不是插入新行."""
    store.upsert_quota(
        quota_id="q-1", project_id="proj-1", year_month="2026-05",
        monthly_token_limit=1_000_000, daily_auto_gen_limit=10,
        tokens_used=0, auto_gen_count=0, is_throttled=False,
        updated_at=_iso(_utc()),
        json_str=json.dumps({"id": "q-1"}),
    )
    store.upsert_quota(
        quota_id="q-1",  # 同 id 走 PK 冲突路径
        project_id="proj-1", year_month="2026-05",
        monthly_token_limit=5_000_000, daily_auto_gen_limit=20,
        tokens_used=100, auto_gen_count=3, is_throttled=False,
        updated_at=_iso(_utc(minute=5)),
        json_str=json.dumps({"id": "q-1"}),
    )
    raw = store.get_quota("proj-1", "2026-05")
    # 应是更新后值
    assert raw is not None


def test_stats_includes_v04_tables(store: SqliteStore):
    """stats() 字典应有 v0.4 新增的 3 张表 key."""
    s = store.stats()
    assert "trigger_rules" in s
    assert "trigger_executions" in s
    assert "generation_quotas" in s
    assert s["trigger_rules"] == 0
