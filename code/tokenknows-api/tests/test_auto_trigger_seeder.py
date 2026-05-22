"""4 条预置规则 seeder (v0.4 T28).

覆盖:
- 空库首次 seed: 4 条全部创建
- 二次 seed (相同 name): 全部跳过 (幂等)
- 部分 seed: 已有 2 条 → 第二次只新增 2 条
- 字段对齐 Proposal 附录 A
- book 规则默认 enabled=false (Q4 决策)
- 其他 3 条默认 enabled=true
- JSON 文件加载逻辑容错 (缺字段使用默认值)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.services import auto_trigger_service as svc
from app.services.auto_trigger.seeder import (
    _DEFAULT_RULE_FILES,
    _load_default_rules,
    seed_default_rules,
)


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    return s


# ─── JSON 加载 ────────────────────────────────────────────


def test_load_default_rules_returns_four():
    rules = _load_default_rules()
    assert len(rules) == 4
    names = {r["name"] for r in rules}
    assert names == {
        "周一 09:00 自动周报",
        "PR 含 architecture-decision label → ADR",
        "Issue 含 incident label → 自动复盘",
        "累积 50 章 approved → 自动书籍",
    }


def test_default_rule_files_match_expected_set():
    """文件名清单应与 Proposal 附录 A 对齐."""
    assert _DEFAULT_RULE_FILES == [
        "weekly_report.json",
        "adr_pr_label.json",
        "incident_issue.json",
        "book_threshold.json",
    ]


def test_book_rule_default_disabled():
    """Q4 决策: book 类型预置规则默认 enabled=false."""
    rules = _load_default_rules()
    book = next(r for r in rules if r["asset_type"] == "book")
    assert book["enabled"] is False


def test_other_rules_default_enabled():
    """其余 3 条默认 enabled=true."""
    rules = _load_default_rules()
    for r in rules:
        if r["asset_type"] != "book":
            assert r["enabled"] is True, f"{r['name']} 应默认启用"


def test_weekly_report_extra_condition():
    """周报规则带 events_last_7d >= 30 的 extra_condition."""
    rules = _load_default_rules()
    weekly = next(r for r in rules if r["asset_type"] == "weekly_report")
    assert weekly["cron_expr"] == "0 9 * * 1"
    assert weekly["extra_condition"]["metric"] == "events_last_7d"
    assert weekly["extra_condition"]["value"] == 30


def test_adr_rule_event_match():
    rules = _load_default_rules()
    adr = next(r for r in rules if r["asset_type"] == "adr")
    assert adr["mode"] == "event"
    assert adr["event_match"]["event_type"] == "github_pr_merged"
    assert "architecture-decision" in adr["event_match"]["label_any"]


def test_incident_rule_priority_100():
    """incident 优先级 100 (最高)."""
    rules = _load_default_rules()
    inc = next(r for r in rules if r["asset_type"] == "incident")
    assert inc["priority"] == 100
    assert "incident" in inc["event_match"]["label_any"]


def test_book_threshold_spec():
    rules = _load_default_rules()
    book = next(r for r in rules if r["asset_type"] == "book")
    assert book["mode"] == "threshold"
    assert book["threshold_spec"]["metric"] == "approved_chapters_total"
    assert book["threshold_spec"]["value"] == 50
    assert book["threshold_spec"]["and_not_exists_asset_of_type"] == "book"


# ─── seed_default_rules 幂等 ──────────────────────────────


def test_seed_default_rules_empty_db(fresh_db):
    result = seed_default_rules()
    assert result["created"] == 4
    assert result["skipped"] == 0
    assert result["errors"] == 0
    # 持久化校验
    rules = svc.list_rules(project_id=None)
    assert len(rules) == 4


def test_seed_default_rules_idempotent(fresh_db):
    """二次 seed 应全部跳过 (name 已存在)."""
    seed_default_rules()  # 第一次 create 4
    result = seed_default_rules()  # 第二次 skip 4
    assert result["created"] == 0
    assert result["skipped"] == 4
    assert result["errors"] == 0
    # 数据库仍是 4 条 (不重复)
    rules = svc.list_rules(project_id=None)
    assert len(rules) == 4


def test_seed_default_rules_partial_existing(fresh_db):
    """已有 2 条同名规则 → 第二次 seed 只新增 2 条."""
    # 手动创建 2 条同名规则
    svc.create_rule(
        project_id=None,
        name="周一 09:00 自动周报",
        mode="cron", asset_type="weekly_report",
        cron_expr="0 9 * * 1",
        created_by="manual",  # 与 seeder 不同 source
    )
    svc.create_rule(
        project_id=None,
        name="累积 50 章 approved → 自动书籍",
        mode="threshold", asset_type="book",
        threshold_spec={
            "metric": "approved_chapters_total",
            "comparator": ">=", "value": 50,
        },
        enabled=False,
        cooldown_seconds=604800,
        daily_cap=1,
        created_by="manual",
    )

    result = seed_default_rules()
    assert result["created"] == 2  # ADR + incident
    assert result["skipped"] == 2  # 周报 + book
    # 用户手动版本保留 (created_by 仍是 manual)
    rules = svc.list_rules(project_id=None)
    weekly = next(r for r in rules if r.asset_type == "weekly_report")
    assert weekly.created_by == "manual"


def test_seeded_rules_have_system_creator(fresh_db):
    """seed 出来的规则 created_by='system'."""
    seed_default_rules()
    rules = svc.list_rules(project_id=None)
    for r in rules:
        assert r.created_by == "system"


def test_seeded_book_rule_disabled(fresh_db):
    """seed 后 book 规则在 DB 里 enabled=False (Q4 决策端到端验证)."""
    seed_default_rules()
    rules = svc.list_rules(project_id=None)
    book = next(r for r in rules if r.asset_type == "book")
    assert book.enabled is False


def test_seeded_rules_all_project_id_none(fresh_db):
    """seed 出来的都是实例级规则 (project_id=None)."""
    seed_default_rules()
    rules = svc.list_rules(project_id=None)
    for r in rules:
        assert r.project_id is None
