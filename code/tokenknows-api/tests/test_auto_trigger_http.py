"""HTTP API · v0.4 T32 端到端.

覆盖:
- 规则 CRUD: list (filter enabled/mode) / get / patch (启停 + cooldown)
- 404: 不存在规则 / 跨项目访问其他项目的规则
- 执行历史: list / get / cancel (409 if not scheduled) / flag-false-positive
- onboarding: GET preview / POST 批量启用
- 错误响应 envelope 一致性
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.auto_trigger import TriggerSignal
from app.services import auto_trigger_service as svc


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


def _create_weekly_rule(project_id: str | None = None, **overrides):
    defaults = dict(
        project_id=project_id,
        name=f"周报-{project_id or 'instance'}",
        mode="cron",
        asset_type="weekly_report",
        cron_expr="0 9 * * 1",
        created_by="system",
    )
    defaults.update(overrides)  # overrides 覆盖默认 name 等
    return svc.create_rule(**defaults)


# ─── Rules CRUD ───────────────────────────────────────────


def test_list_rules_empty(client):
    res = client.get("/api/v1/projects/proj-1/auto-triggers/rules")
    assert res.status_code == 200
    assert res.json() == {"data": []}


def test_list_rules_returns_instance_and_project_rules(client):
    _create_weekly_rule(project_id=None)
    _create_weekly_rule(project_id="proj-1")
    _create_weekly_rule(project_id="proj-other")  # 不应在 proj-1 视角下出现

    res = client.get("/api/v1/projects/proj-1/auto-triggers/rules")
    data = res.json()["data"]
    names = {r["name"] for r in data}
    assert names == {"周报-instance", "周报-proj-1"}


def test_list_rules_filter_enabled(client):
    _create_weekly_rule(project_id="proj-1", name="active-rule")
    _create_weekly_rule(project_id="proj-1", name="paused-rule", enabled=False)

    res = client.get("/api/v1/projects/proj-1/auto-triggers/rules?enabled=true")
    names = {r["name"] for r in res.json()["data"]}
    assert "active-rule" in names
    assert "paused-rule" not in names


def test_list_rules_filter_mode(client):
    _create_weekly_rule(project_id="proj-1")  # cron
    svc.create_rule(
        project_id="proj-1", name="evt", mode="event", asset_type="adr",
        event_match={"event_type": "github_pr_merged"},
        created_by="user",
    )
    res = client.get("/api/v1/projects/proj-1/auto-triggers/rules?mode=event")
    names = {r["name"] for r in res.json()["data"]}
    assert names == {"evt"}


def test_get_rule_happy(client):
    rule = _create_weekly_rule(project_id="proj-1")
    res = client.get(f"/api/v1/projects/proj-1/auto-triggers/rules/{rule.id}")
    assert res.status_code == 200
    assert res.json()["id"] == rule.id


def test_get_rule_404_when_missing(client):
    res = client.get("/api/v1/projects/proj-1/auto-triggers/rules/rule-nope")
    assert res.status_code == 404


def test_get_rule_404_cross_project(client):
    """proj-other 的规则在 proj-1 视角下应不可见."""
    rule = _create_weekly_rule(project_id="proj-other")
    res = client.get(f"/api/v1/projects/proj-1/auto-triggers/rules/{rule.id}")
    assert res.status_code == 404


def test_get_rule_instance_visible_to_all_projects(client):
    """实例级规则 (project_id=None) 任何项目都能看到."""
    rule = _create_weekly_rule(project_id=None)
    res = client.get(f"/api/v1/projects/proj-X/auto-triggers/rules/{rule.id}")
    assert res.status_code == 200


def test_patch_rule_toggle_enabled(client):
    rule = _create_weekly_rule(project_id="proj-1")
    assert rule.enabled is True
    res = client.patch(
        f"/api/v1/projects/proj-1/auto-triggers/rules/{rule.id}",
        json={"enabled": False},
    )
    assert res.status_code == 200
    assert res.json()["enabled"] is False


def test_patch_rule_cooldown(client):
    rule = _create_weekly_rule(project_id="proj-1")
    res = client.patch(
        f"/api/v1/projects/proj-1/auto-triggers/rules/{rule.id}",
        json={"cooldown_seconds": 7200, "daily_cap": 3},
    )
    body = res.json()
    assert body["cooldown_seconds"] == 7200
    assert body["daily_cap"] == 3


def test_patch_rule_empty_body_noop(client):
    rule = _create_weekly_rule(project_id="proj-1")
    res = client.patch(
        f"/api/v1/projects/proj-1/auto-triggers/rules/{rule.id}",
        json={},
    )
    assert res.status_code == 200
    assert res.json()["id"] == rule.id


def test_patch_rule_404(client):
    res = client.patch(
        "/api/v1/projects/proj-1/auto-triggers/rules/rule-nope",
        json={"enabled": False},
    )
    assert res.status_code == 404


# ─── Executions ───────────────────────────────────────────


def _schedule(rule, project_id="proj-1"):
    return svc.schedule_execution(
        rule, project_id, signal=TriggerSignal(type="cron", summary="test")
    )


def test_list_executions_empty(client):
    res = client.get("/api/v1/projects/proj-1/auto-triggers/executions")
    assert res.status_code == 200
    assert res.json() == {"data": []}


def test_list_executions_project_isolation(client):
    rule = _create_weekly_rule(project_id=None)
    _schedule(rule, "proj-1")
    _schedule(rule, "proj-other")

    res = client.get("/api/v1/projects/proj-1/auto-triggers/executions")
    data = res.json()["data"]
    assert len(data) == 1
    assert data[0]["project_id"] == "proj-1"


def test_list_executions_filter_status(client):
    rule = _create_weekly_rule(project_id="proj-1")
    e1 = _schedule(rule, "proj-1")
    svc.cancel_execution(e1.id, by_user=True)
    _schedule(rule, "proj-1")  # 另一条 scheduled

    res = client.get(
        "/api/v1/projects/proj-1/auto-triggers/executions?status=canceled"
    )
    data = res.json()["data"]
    assert len(data) == 1
    assert data[0]["status"] == "canceled"


def test_list_executions_filter_rule(client):
    r1 = _create_weekly_rule(project_id="proj-1", name="r1")
    r2 = _create_weekly_rule(project_id="proj-1", name="r2")
    _schedule(r1, "proj-1")
    _schedule(r2, "proj-1")
    res = client.get(
        f"/api/v1/projects/proj-1/auto-triggers/executions?rule_id={r1.id}"
    )
    data = res.json()["data"]
    assert all(e["rule_id"] == r1.id for e in data)


def test_get_execution_happy(client):
    rule = _create_weekly_rule(project_id="proj-1")
    exe = _schedule(rule, "proj-1")
    res = client.get(
        f"/api/v1/projects/proj-1/auto-triggers/executions/{exe.id}"
    )
    assert res.status_code == 200
    assert res.json()["id"] == exe.id


def test_get_execution_cross_project_404(client):
    rule = _create_weekly_rule(project_id=None)
    exe = _schedule(rule, "proj-other")
    res = client.get(
        f"/api/v1/projects/proj-1/auto-triggers/executions/{exe.id}"
    )
    assert res.status_code == 404


def test_cancel_execution_happy(client):
    rule = _create_weekly_rule(project_id="proj-1")
    exe = _schedule(rule, "proj-1")
    res = client.post(
        f"/api/v1/projects/proj-1/auto-triggers/executions/{exe.id}/cancel"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "canceled"
    assert body["user_canceled"] is True


def test_cancel_execution_409_when_already_fired(client):
    rule = _create_weekly_rule(project_id="proj-1")
    exe = _schedule(rule, "proj-1")
    svc.mark_fired(exe.id, asset_id="asset-99")

    res = client.post(
        f"/api/v1/projects/proj-1/auto-triggers/executions/{exe.id}/cancel"
    )
    assert res.status_code == 409


def test_cancel_execution_404(client):
    res = client.post(
        "/api/v1/projects/proj-1/auto-triggers/executions/exec-nope/cancel"
    )
    assert res.status_code == 404


def test_flag_false_positive_happy(client):
    rule = _create_weekly_rule(project_id="proj-1")
    exe = _schedule(rule, "proj-1")
    res = client.post(
        f"/api/v1/projects/proj-1/auto-triggers/executions/{exe.id}/flag-false-positive"
    )
    assert res.status_code == 200
    assert res.json()["user_flagged_false_positive"] is True


def test_flag_false_positive_works_on_fired(client):
    """误触发可在任意状态下标记 (含已 fired 的事后反馈)."""
    rule = _create_weekly_rule(project_id="proj-1")
    exe = _schedule(rule, "proj-1")
    svc.mark_fired(exe.id, asset_id="asset-99")

    res = client.post(
        f"/api/v1/projects/proj-1/auto-triggers/executions/{exe.id}/flag-false-positive"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user_flagged_false_positive"] is True
    assert body["status"] == "fired"  # status 不变


# ─── Onboarding ───────────────────────────────────────────


def test_onboarding_preview(client):
    _create_weekly_rule(project_id=None, name="default-1")
    _create_weekly_rule(project_id=None, name="default-2")
    res = client.get("/api/v1/projects/proj-X/auto-triggers/onboarding")
    assert res.status_code == 200
    body = res.json()
    names = {r["name"] for r in body["default_rules"]}
    assert names == {"default-1", "default-2"}


def test_onboarding_enable_selected(client):
    r1 = _create_weekly_rule(project_id=None, name="r1", enabled=False)
    r2 = _create_weekly_rule(project_id=None, name="r2", enabled=False)
    r3 = _create_weekly_rule(project_id=None, name="r3", enabled=False)

    res = client.post(
        "/api/v1/projects/proj-1/auto-triggers/onboarding",
        json={"enabled_rule_ids": [r1.id, r3.id]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["enabled_count"] == 2
    assert body["skipped_count"] == 1

    # 验证 DB 状态
    assert svc.get_rule(r1.id).enabled is True
    assert svc.get_rule(r2.id).enabled is False  # 未选中
    assert svc.get_rule(r3.id).enabled is True


def test_onboarding_enable_empty_disables_all(client):
    r1 = _create_weekly_rule(project_id=None, name="r1", enabled=True)
    r2 = _create_weekly_rule(project_id=None, name="r2", enabled=True)
    res = client.post(
        "/api/v1/projects/proj-1/auto-triggers/onboarding",
        json={"enabled_rule_ids": []},
    )
    assert res.status_code == 200
    assert res.json()["enabled_count"] == 0
    assert res.json()["skipped_count"] == 2
    assert svc.get_rule(r1.id).enabled is False
    assert svc.get_rule(r2.id).enabled is False
