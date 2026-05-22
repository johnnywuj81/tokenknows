"""ThresholdEvaluator (v0.4.2 T41).

覆盖:
- metric resolver: approved_chapters_total / events_count_30d / unsupported
- 6 种 comparator (>=, <=, ==, !=, >, <)
- and_not_exists_asset_of_type 去重 (book 一项目一份)
- cooldown / daily_cap 复用
- 实例级规则 fan-out 到所有 active 项目
- 项目级规则隔离
- 端到端: 累积 50 章 → 触发 book schedule
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.auto_trigger import ThresholdSpec, TriggerSignal
from app.services import auto_trigger_service as svc
from app.services.auto_trigger.evaluator.threshold_evaluator import (
    _check_threshold,
    _compare,
    _count_approved_chapters,
    _has_asset_of_type,
    _resolve_metric,
    evaluate_threshold_rules,
)


# ─── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """每个 test: 独立 SQLite + 重置 generation_service 内存 cache."""
    from app.services import generation_service

    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)

    # 重置 generation_service 模块级状态
    monkeypatch.setattr(generation_service, "_assets", {})
    monkeypatch.setattr(generation_service, "_chapters", {})
    monkeypatch.setattr(generation_service, "_progress", {})
    return s


def _make_asset(
    project_id: str, asset_type: str = "weekly_report",
    asset_id: str | None = None, status: str = "draft",
):
    """直接插入到 generation_service 内存 cache (跳过真实 LLM 调用)."""
    from app.schemas.asset import Asset
    from app.services import generation_service
    from uuid import uuid4

    now = datetime.now(timezone.utc)
    asset_id = asset_id or f"asset-{uuid4().hex[:8]}"
    a = Asset(
        id=asset_id, project_id=project_id, type=asset_type,
        title=f"test-{asset_id}", status=status, current_version=1,
        template_id=f"tpl-{asset_type}", created_by="test",
        created_at=now, updated_at=now,
    )
    generation_service._assets[asset_id] = a
    generation_service._chapters[asset_id] = []
    return a


def _add_approved_chapters(asset_id: str, n: int):
    from app.schemas.asset import Chapter
    from app.services import generation_service

    for i in range(n):
        ch = Chapter(
            id=f"{asset_id}-c{i}",
            asset_id=asset_id,
            order_index=i,
            title=f"§{i+1}",
            content=f"内容 {i}",
            approval_state="approved",
        )
        generation_service._chapters[asset_id].append(ch)


# ─── _compare ─────────────────────────────────────────────


def test_compare_all_operators():
    assert _compare(50, ">=", 50) is True
    assert _compare(49, ">=", 50) is False
    assert _compare(50, "<=", 50) is True
    assert _compare(50, "==", 50) is True
    assert _compare(50, "!=", 51) is True
    assert _compare(51, ">", 50) is True
    assert _compare(49, "<", 50) is True


def test_compare_unknown_raises():
    with pytest.raises(ValueError):
        _compare(1, "??", 0)


# ─── _resolve_metric ──────────────────────────────────────


def test_resolve_metric_approved_chapters_total(fresh_db):
    a1 = _make_asset("proj-1")
    a2 = _make_asset("proj-1")
    _add_approved_chapters(a1.id, 30)
    _add_approved_chapters(a2.id, 25)
    val = _resolve_metric("approved_chapters_total", "proj-1", datetime.now(timezone.utc))
    assert val == 55


def test_resolve_metric_other_project_isolated(fresh_db):
    a1 = _make_asset("proj-1")
    _add_approved_chapters(a1.id, 50)
    a2 = _make_asset("proj-other")
    _add_approved_chapters(a2.id, 30)
    val = _resolve_metric("approved_chapters_total", "proj-1", datetime.now(timezone.utc))
    assert val == 50  # 不包含 proj-other 的


def test_resolve_metric_events_count_30d(fresh_db):
    # 插入 5 个 events (10 天内)
    now = datetime.now(timezone.utc)
    for i in range(5):
        fresh_db.upsert_event(
            event_id=f"e{i}", project_id="proj-1", source_type="github",
            event_type="commit",
            occurred_at=(now - timedelta(days=i)).isoformat(),
            ingested_at=now.isoformat(),
            content_hash=f"h{i}", json_str=json.dumps({"id": f"e{i}"}),
        )
    val = _resolve_metric("events_count_30d", "proj-1", now)
    assert val == 5


def test_resolve_metric_unsupported_returns_none(fresh_db):
    val = _resolve_metric("nonexistent_metric_v9", "proj-1", datetime.now(timezone.utc))
    assert val is None


# ─── _has_asset_of_type ──────────────────────────────────


def test_has_asset_of_type_true(fresh_db):
    _make_asset("proj-1", asset_type="book")
    assert _has_asset_of_type("proj-1", "book") is True


def test_has_asset_of_type_excludes_archived(fresh_db):
    _make_asset("proj-1", asset_type="book", status="archived")
    assert _has_asset_of_type("proj-1", "book") is False


def test_has_asset_of_type_false(fresh_db):
    _make_asset("proj-1", asset_type="weekly_report")
    assert _has_asset_of_type("proj-1", "book") is False


# ─── _check_threshold ────────────────────────────────────


def test_check_threshold_passes(fresh_db):
    a = _make_asset("proj-1")
    _add_approved_chapters(a.id, 50)
    spec = ThresholdSpec(
        metric="approved_chapters_total", comparator=">=", value=50,
    )
    passed, actual, reason = _check_threshold(spec, "proj-1", datetime.now(timezone.utc))
    assert passed is True
    assert actual == 50
    assert reason is None


def test_check_threshold_fails_below(fresh_db):
    a = _make_asset("proj-1")
    _add_approved_chapters(a.id, 30)
    spec = ThresholdSpec(metric="approved_chapters_total", comparator=">=", value=50)
    passed, actual, reason = _check_threshold(spec, "proj-1", datetime.now(timezone.utc))
    assert passed is False
    assert actual == 30
    assert reason and "不满足" in reason


def test_check_threshold_and_not_exists_blocks(fresh_db):
    """已有 book → and_not_exists 触发, 不命中."""
    a = _make_asset("proj-1")
    _add_approved_chapters(a.id, 50)
    _make_asset("proj-1", asset_type="book")  # 已存在 book
    spec = ThresholdSpec(
        metric="approved_chapters_total", comparator=">=", value=50,
        and_not_exists_asset_of_type="book",
    )
    passed, actual, reason = _check_threshold(spec, "proj-1", datetime.now(timezone.utc))
    assert passed is False
    assert actual == 50
    assert reason and "book" in reason


def test_check_threshold_unsupported_metric(fresh_db):
    spec = ThresholdSpec(metric="future_v9_metric", comparator=">=", value=10)
    passed, _, reason = _check_threshold(spec, "proj-1", datetime.now(timezone.utc))
    assert passed is False
    assert reason and "unsupported" in reason


# ─── evaluate_threshold_rules 主流程 ─────────────────────


def _create_book_rule(**overrides):
    defaults = dict(
        project_id=None,
        name="累积 50 章 → book",
        mode="threshold",
        asset_type="book",
        threshold_spec=ThresholdSpec(
            metric="approved_chapters_total", comparator=">=", value=50,
            and_not_exists_asset_of_type="book",
        ),
        priority=70,
        created_by="system",
        cooldown_seconds=604800,
        daily_cap=1,
    )
    defaults.update(overrides)
    return svc.create_rule(**defaults)


def test_evaluate_hit_schedules(fresh_db):
    rule = _create_book_rule()
    # 在 proj-1 准备 50 章 approved + 至少 1 个 event 让它出现在 active_projects
    a = _make_asset("proj-1")
    _add_approved_chapters(a.id, 50)
    fresh_db.upsert_event(
        event_id="e1", project_id="proj-1", source_type="github",
        event_type="commit", occurred_at=datetime.now(timezone.utc).isoformat(),
        ingested_at=datetime.now(timezone.utc).isoformat(),
        content_hash="h1", json_str="{}",
    )

    stats = evaluate_threshold_rules()
    assert stats["scheduled"] == 1

    execs = svc.list_executions(project_id="proj-1")
    assert len(execs) == 1
    assert execs[0].signal.type == "threshold_scan"
    assert execs[0].rule_id == rule.id


def test_evaluate_not_satisfied_no_schedule(fresh_db):
    _create_book_rule()
    a = _make_asset("proj-1")
    _add_approved_chapters(a.id, 30)  # < 50
    fresh_db.upsert_event(
        event_id="e1", project_id="proj-1", source_type="github",
        event_type="commit", occurred_at=datetime.now(timezone.utc).isoformat(),
        ingested_at=datetime.now(timezone.utc).isoformat(),
        content_hash="h1", json_str="{}",
    )
    stats = evaluate_threshold_rules()
    assert stats["scheduled"] == 0
    assert stats["not_satisfied"] == 1


def test_evaluate_and_not_exists_blocks(fresh_db):
    _create_book_rule()
    a = _make_asset("proj-1")
    _add_approved_chapters(a.id, 100)
    _make_asset("proj-1", asset_type="book")  # 已有 book
    fresh_db.upsert_event(
        event_id="e1", project_id="proj-1", source_type="github",
        event_type="commit", occurred_at=datetime.now(timezone.utc).isoformat(),
        ingested_at=datetime.now(timezone.utc).isoformat(),
        content_hash="h1", json_str="{}",
    )
    stats = evaluate_threshold_rules()
    assert stats["scheduled"] == 0


def test_evaluate_cooldown_blocks(fresh_db):
    rule = _create_book_rule(cooldown_seconds=3600)
    a = _make_asset("proj-1")
    _add_approved_chapters(a.id, 50)
    fresh_db.upsert_event(
        event_id="e1", project_id="proj-1", source_type="github",
        event_type="commit", occurred_at=datetime.now(timezone.utc).isoformat(),
        ingested_at=datetime.now(timezone.utc).isoformat(),
        content_hash="h1", json_str="{}",
    )
    # 先 fire 一次
    exe = svc.schedule_execution(rule, "proj-1", TriggerSignal(type="manual", summary="pre"))
    svc.mark_fired(exe.id, "asset-prior")
    # 此时 cooldown 仍内 → 跳过
    stats = evaluate_threshold_rules()
    assert stats["skipped_cooldown"] == 1
    assert stats["scheduled"] == 0


def test_evaluate_instance_rule_fans_out(fresh_db):
    """实例级 threshold 规则 → 对所有 active 项目 evaluate."""
    _create_book_rule()
    for pid in ("proj-A", "proj-B"):
        a = _make_asset(pid)
        _add_approved_chapters(a.id, 50)
        fresh_db.upsert_event(
            event_id=f"e-{pid}", project_id=pid, source_type="github",
            event_type="commit", occurred_at=datetime.now(timezone.utc).isoformat(),
            ingested_at=datetime.now(timezone.utc).isoformat(),
            content_hash=f"h-{pid}", json_str="{}",
        )
    stats = evaluate_threshold_rules()
    assert stats["checks"] == 2  # 两个项目都被评估
    assert stats["scheduled"] == 2


def test_evaluate_project_rule_isolates(fresh_db):
    """项目级 threshold 规则 → 仅评估自己 project."""
    _create_book_rule(project_id="proj-A")
    for pid in ("proj-A", "proj-B"):
        a = _make_asset(pid)
        _add_approved_chapters(a.id, 50)
        fresh_db.upsert_event(
            event_id=f"e-{pid}", project_id=pid, source_type="github",
            event_type="commit", occurred_at=datetime.now(timezone.utc).isoformat(),
            ingested_at=datetime.now(timezone.utc).isoformat(),
            content_hash=f"h-{pid}", json_str="{}",
        )
    stats = evaluate_threshold_rules()
    assert stats["scheduled"] == 1  # 只 proj-A


def test_evaluate_disabled_rule_ignored(fresh_db):
    _create_book_rule(enabled=False)
    a = _make_asset("proj-1")
    _add_approved_chapters(a.id, 50)
    stats = evaluate_threshold_rules()
    assert stats["rules_evaluated"] == 0


def test_evaluate_no_threshold_rules_empty_stats(fresh_db):
    """无 threshold 规则 → 早退, 返 zero stats."""
    stats = evaluate_threshold_rules()
    assert stats["rules_evaluated"] == 0
    assert stats["scheduled"] == 0
