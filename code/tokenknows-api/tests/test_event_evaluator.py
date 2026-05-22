"""EventEvaluator + GitHub webhook 集成 (v0.4.1 T40).

覆盖:
- normalize_pr_webhook / normalize_issue_webhook 边界
- _match_event: event_type / label_any / file_glob / title_contains
- evaluate_github_event 主流程: 命中 schedule / cooldown / daily_cap / 无匹配
- 优先级路由: 同 asset_type 高 priority 命中后低 priority 不再触发
- 端到端 GitHub webhook POST → schedule_execution 入库
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time

from app.main import app
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.auto_trigger import EventMatch, TriggerSignal
from app.services import auto_trigger_service as svc
from app.services.auto_trigger.evaluator.event_evaluator import (
    GitHubEvent,
    _match_event,
    evaluate_github_event,
    normalize_issue_webhook,
    normalize_pr_webhook,
)


# ─── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    return s


@pytest.fixture
def client(fresh_db) -> TestClient:
    return TestClient(app)


def _create_adr_rule(**overrides):
    defaults = dict(
        project_id=None,
        name="PR architecture → ADR",
        mode="event",
        asset_type="adr",
        event_match=EventMatch(
            event_type="github_pr_merged",
            label_any=["architecture-decision", "adr"],
        ),
        priority=85,
        created_by="system",
    )
    defaults.update(overrides)
    return svc.create_rule(**defaults)


def _create_incident_rule(**overrides):
    defaults = dict(
        project_id=None,
        name="Issue incident → 复盘",
        mode="event",
        asset_type="incident",
        event_match=EventMatch(
            event_type="github_issue_opened",
            label_any=["incident", "outage"],
        ),
        priority=100,
        created_by="system",
    )
    defaults.update(overrides)
    return svc.create_rule(**defaults)


# ─── Normalize PR webhook ─────────────────────────────────


def test_normalize_pr_opened():
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42, "title": "Add ADR",
            "labels": [{"name": "adr"}, {"name": "size:L"}],
            "merged": False,
        },
        "repository": {"full_name": "acme/api"},
    }
    ev = normalize_pr_webhook(payload)
    assert ev is not None
    assert ev.event_type == "github_pr_opened"
    assert ev.repo == "acme/api"
    assert ev.number == 42
    assert set(ev.labels) == {"adr", "size:L"}


def test_normalize_pr_merged():
    payload = {
        "action": "closed",
        "pull_request": {
            "number": 99, "title": "Merge migration",
            "labels": [{"name": "architecture-decision"}],
            "merged": True,
        },
        "repository": {"full_name": "acme/api"},
    }
    ev = normalize_pr_webhook(payload)
    assert ev is not None
    assert ev.event_type == "github_pr_merged"
    assert "architecture-decision" in ev.labels


def test_normalize_pr_closed_not_merged():
    payload = {
        "action": "closed",
        "pull_request": {
            "number": 1, "title": "abandon", "labels": [], "merged": False
        },
        "repository": {"full_name": "x/y"},
    }
    ev = normalize_pr_webhook(payload)
    assert ev is not None
    assert ev.event_type == "github_pr_closed"


def test_normalize_pr_ignored_actions():
    """labeled / assigned / review_requested 不触发自动规则."""
    for action in ("labeled", "assigned", "review_requested", "edited"):
        payload = {
            "action": action,
            "pull_request": {"number": 1, "title": "x", "labels": [], "merged": False},
            "repository": {"full_name": "x/y"},
        }
        assert normalize_pr_webhook(payload) is None, f"action={action} 不应触发"


# ─── Normalize Issue webhook ──────────────────────────────


def test_normalize_issue_opened():
    payload = {
        "action": "opened",
        "issue": {
            "number": 7, "title": "Login fails",
            "labels": [{"name": "incident"}, {"name": "p0"}],
        },
        "repository": {"full_name": "acme/api"},
    }
    ev = normalize_issue_webhook(payload)
    assert ev is not None
    assert ev.event_type == "github_issue_opened"
    assert ev.labels == ["incident", "p0"]


def test_normalize_issue_skips_pr_comment():
    """GitHub 把 PR 评论也吐到 issues endpoint; 跳过."""
    payload = {
        "action": "opened",
        "issue": {"number": 1, "pull_request": {"url": "..."}, "title": "x", "labels": []},
        "repository": {"full_name": "x/y"},
    }
    assert normalize_issue_webhook(payload) is None


# ─── _match_event 边界 ────────────────────────────────────


def _make_event(**kw):
    defaults = dict(
        event_type="github_pr_merged", repo="x/y", number=1,
        title="", labels=[], files_changed=[], raw={},
    )
    defaults.update(kw)
    return GitHubEvent(**defaults)


def test_match_event_type_mismatch():
    ev = _make_event(event_type="github_issue_opened")
    em = EventMatch(event_type="github_pr_merged")
    ok, _ = _match_event(ev, em)
    assert ok is False


def test_match_label_any_hit():
    ev = _make_event(labels=["adr", "size:S"])
    em = EventMatch(event_type="github_pr_merged", label_any=["adr"])
    ok, _ = _match_event(ev, em)
    assert ok is True


def test_match_label_any_case_insensitive():
    ev = _make_event(labels=["ADR"])
    em = EventMatch(event_type="github_pr_merged", label_any=["adr"])
    ok, _ = _match_event(ev, em)
    assert ok is True


def test_match_label_any_no_intersect():
    ev = _make_event(labels=["size:S"])
    em = EventMatch(event_type="github_pr_merged", label_any=["adr", "architecture-decision"])
    ok, _ = _match_event(ev, em)
    assert ok is False


def test_match_label_any_empty_skipped():
    """label_any 为空 = 不校验 labels."""
    ev = _make_event(labels=[])
    em = EventMatch(event_type="github_pr_merged", label_any=[])
    ok, _ = _match_event(ev, em)
    assert ok is True


def test_match_file_glob_hit():
    ev = _make_event(files_changed=["docs/design/clickhouse.md", "src/db.py"])
    em = EventMatch(event_type="github_pr_merged", file_glob=["docs/design/**"])
    ok, _ = _match_event(ev, em)
    assert ok is True


def test_match_file_glob_no_match():
    ev = _make_event(files_changed=["src/main.py"])
    em = EventMatch(event_type="github_pr_merged", file_glob=["docs/**"])
    ok, _ = _match_event(ev, em)
    assert ok is False


def test_match_title_contains():
    ev = _make_event(title="[ADR] Switch DB")
    em = EventMatch(event_type="github_pr_merged", title_contains=["[adr]"])
    ok, _ = _match_event(ev, em)
    assert ok is True  # case insensitive


def test_match_title_not_contains():
    ev = _make_event(title="Fix typo")
    em = EventMatch(event_type="github_pr_merged", title_contains=["[adr]"])
    ok, _ = _match_event(ev, em)
    assert ok is False


# ─── evaluate_github_event 主流程 ─────────────────────────


def test_evaluate_event_hit_schedules(fresh_db):
    _create_adr_rule()
    ev = _make_event(
        event_type="github_pr_merged",
        labels=["architecture-decision"],
        title="Switch from Postgres to ClickHouse",
    )
    stats = evaluate_github_event(ev, "proj-1")
    assert stats["matched"] == 1
    assert stats["scheduled"] == 1

    # execution 入库
    execs = svc.list_executions(project_id="proj-1")
    assert len(execs) == 1
    assert execs[0].status == "scheduled"
    assert execs[0].signal.type == "github_webhook"


def test_evaluate_event_no_match_no_schedule(fresh_db):
    _create_adr_rule()
    ev = _make_event(labels=["bug"])  # 没有 adr label
    stats = evaluate_github_event(ev, "proj-1")
    assert stats["matched"] == 0
    assert stats["scheduled"] == 0
    assert svc.list_executions(project_id="proj-1") == []


def test_evaluate_event_cooldown(fresh_db):
    rule = _create_adr_rule(cooldown_seconds=3600)
    # 先 fire 一次
    exe = svc.schedule_execution(rule, "proj-1", TriggerSignal(type="manual", summary="pre"))
    svc.mark_fired(exe.id, "asset-prior")
    # 再来 event 应被 cooldown 跳过
    ev = _make_event(labels=["adr"])
    stats = evaluate_github_event(ev, "proj-1")
    assert stats["skipped_cooldown"] == 1
    assert stats["scheduled"] == 0


def test_evaluate_event_priority_routing(fresh_db):
    """同一 asset_type 两条规则同时命中, 只取高 priority."""
    high = _create_adr_rule(name="high-prio", priority=90)
    low = _create_adr_rule(name="low-prio", priority=50)
    ev = _make_event(labels=["adr"])
    stats = evaluate_github_event(ev, "proj-1")
    assert stats["scheduled"] == 1
    execs = svc.list_executions(project_id="proj-1")
    # 应是 high 那条
    assert execs[0].rule_id == high.id


def test_evaluate_event_different_asset_types_both_fire(fresh_db):
    """两条规则 asset_type 不同 → 都 schedule."""
    _create_adr_rule()
    # 创建另一条 PR merged 但 asset_type=tech_design
    svc.create_rule(
        project_id=None, name="PR merged → tech_design", mode="event",
        asset_type="tech_design",
        event_match=EventMatch(
            event_type="github_pr_merged", label_any=["architecture-decision"]
        ),
        priority=80, created_by="system",
    )
    ev = _make_event(labels=["architecture-decision"])
    stats = evaluate_github_event(ev, "proj-1")
    assert stats["scheduled"] == 2  # 两条不同类型都触发


def test_evaluate_event_disabled_rule_ignored(fresh_db):
    _create_adr_rule(enabled=False)
    ev = _make_event(labels=["adr"])
    stats = evaluate_github_event(ev, "proj-1")
    assert stats["rules_evaluated"] == 0


# ─── 端到端: GitHub webhook → schedule ────────────────────


def test_webhook_pr_merged_schedules_adr(client, monkeypatch):
    """POST /webhooks/github (pull_request closed+merged with adr label) →
    EventEvaluator 命中 ADR 规则 → schedule_execution 入库."""
    _create_adr_rule()
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)  # 跳过验签

    payload = {
        "action": "closed",
        "pull_request": {
            "number": 1234,
            "title": "[ADR] Switch to ClickHouse",
            "body": "...",
            "merged": True,
            "merged_at": "2026-05-22T16:00:00Z",
            "updated_at": "2026-05-22T16:00:00Z",
            "state": "closed",
            "labels": [{"name": "architecture-decision"}],
            "user": {"login": "alice", "id": 1},
            "html_url": "https://github.com/x/y/pull/1234",
            "head": {"ref": "feat"}, "base": {"ref": "main"},
        },
        "repository": {"full_name": "acme/api"},
    }
    res = client.post(
        "/api/v1/webhooks/github",
        json=payload,
        headers={"X-GitHub-Event": "pull_request"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["auto_trigger"]["scheduled"] == 1

    # 验 execution 入库
    execs = svc.list_executions(status="scheduled")
    assert len(execs) == 1
    assert execs[0].signal.type == "github_webhook"


def test_webhook_pr_merged_no_label_no_schedule(client, monkeypatch):
    """PR merged 但无 adr label → 不命中规则; webhook 仍 200 但 scheduled=0."""
    _create_adr_rule()
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    payload = {
        "action": "closed",
        "pull_request": {
            "number": 1, "title": "fix typo", "body": "", "merged": True,
            "merged_at": "2026-05-22T16:00:00Z", "updated_at": "2026-05-22T16:00:00Z",
            "state": "closed",
            "labels": [{"name": "bug"}],
            "user": {"login": "bob", "id": 2},
            "html_url": "https://github.com/x/y/pull/1",
            "head": {"ref": "f"}, "base": {"ref": "m"},
        },
        "repository": {"full_name": "x/y"},
    }
    res = client.post(
        "/api/v1/webhooks/github",
        json=payload,
        headers={"X-GitHub-Event": "pull_request"},
    )
    assert res.status_code == 200
    assert res.json()["auto_trigger"]["scheduled"] == 0


def test_webhook_issue_incident_schedules_postmortem(client, monkeypatch):
    _create_incident_rule()
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    payload = {
        "action": "opened",
        "issue": {
            "number": 88, "title": "Login fails for all users", "body": "p0",
            "state": "open",
            "updated_at": "2026-05-22T16:00:00Z",
            "labels": [{"name": "incident"}, {"name": "p0"}],
            "user": {"login": "oncall", "id": 9},
            "html_url": "https://github.com/x/y/issues/88",
        },
        "repository": {"full_name": "acme/api"},
    }
    res = client.post(
        "/api/v1/webhooks/github",
        json=payload,
        headers={"X-GitHub-Event": "issues"},
    )
    assert res.status_code == 200
    assert res.json()["auto_trigger"]["scheduled"] == 1
    execs = svc.list_executions(status="scheduled")
    assert execs[0].rule_id  # 关联到 incident rule


def test_webhook_ping_pong(client):
    res = client.post(
        "/api/v1/webhooks/github",
        json={},
        headers={"X-GitHub-Event": "ping"},
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True, "pong": True}
