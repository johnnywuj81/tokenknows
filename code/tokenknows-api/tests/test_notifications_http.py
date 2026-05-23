"""T49+T51 · /me/notifications HTTP endpoints.

v1.0.1 review fix: 所有端点 require X-User-Id session, query.user_id 必须等于 session.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.http_api.notifications import router as notif_router
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.notification import WebNotification


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    return s


@pytest.fixture
def client(fresh_db) -> TestClient:
    app = FastAPI()
    app.include_router(notif_router)
    return TestClient(app)


def _h(user_id: str) -> dict[str, str]:
    """X-User-Id header helper (v1.0.1 ACL)."""
    return {"X-User-Id": user_id}


def _seed(db, user_id: str, *, count: int = 3, read: bool = False) -> list[str]:
    now = datetime.now(timezone.utc)
    ids = []
    for i in range(count):
        n = WebNotification(
            id=f"n-{user_id}-{i}",
            user_id=user_id,
            type="consent_request",
            title=f"t{i}", body=f"b{i}",
            link_url="/skills/x",
            read=read,
            created_at=now,
            related_skill_id="skill-x",
        )
        db.upsert_notification(
            notification_id=n.id, user_id=n.user_id, type_=n.type,
            related_skill_id=n.related_skill_id, read=n.read,
            created_at=n.created_at.isoformat(),
            json_str=n.model_dump_json(),
        )
        ids.append(n.id)
    return ids


def test_list_notifications_user_filter(client, fresh_db):
    _seed(fresh_db, "ou-a", count=2)
    _seed(fresh_db, "ou-b", count=1)
    r = client.get("/me/notifications?user_id=ou-a", headers=_h("ou-a"))
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert body["unread_count"] == 2
    for n in body["items"]:
        assert n["user_id"] == "ou-a"


def test_list_notifications_unread_only(client, fresh_db):
    fresh_db._exec("DELETE FROM notifications", ())
    _seed(fresh_db, "ou-a", count=2, read=False)
    n = WebNotification(
        id="n-read-1", user_id="ou-a", type="consent_request",
        title="t", body="b", link_url="/x", read=True,
        created_at=datetime.now(timezone.utc), related_skill_id=None,
    )
    fresh_db.upsert_notification(
        notification_id=n.id, user_id=n.user_id, type_=n.type,
        related_skill_id=n.related_skill_id, read=True,
        created_at=n.created_at.isoformat(), json_str=n.model_dump_json(),
    )
    r = client.get(
        "/me/notifications?user_id=ou-a&unread_only=true", headers=_h("ou-a")
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert body["unread_count"] == 2


def test_list_notifications_limit_bounds(client, fresh_db):
    _seed(fresh_db, "ou-a", count=5)
    r = client.get(
        "/me/notifications?user_id=ou-a&limit=3", headers=_h("ou-a")
    )
    assert r.status_code == 200
    assert len(r.json()["items"]) == 3


def test_list_notifications_user_id_required(client):
    """缺 user_id query → 422 (Pydantic)."""
    r = client.get("/me/notifications", headers=_h("ou-a"))
    assert r.status_code == 422


def test_list_notifications_requires_session(client, fresh_db):
    """v1.0.1: 缺 X-User-Id → 401."""
    _seed(fresh_db, "ou-a", count=2)
    r = client.get("/me/notifications?user_id=ou-a")
    assert r.status_code == 401


def test_list_notifications_session_mismatch_blocked(client, fresh_db):
    """v1.0.1: session 不匹配 query → 403 (防订阅他人)."""
    _seed(fresh_db, "ou-a", count=2)
    r = client.get(
        "/me/notifications?user_id=ou-a", headers=_h("ou-attacker")
    )
    assert r.status_code == 403


def test_unread_count(client, fresh_db):
    _seed(fresh_db, "ou-a", count=3)
    r = client.get(
        "/me/notifications/unread-count?user_id=ou-a", headers=_h("ou-a")
    )
    assert r.status_code == 200
    assert r.json()["unread_count"] == 3


def test_unread_count_zero_for_unknown_user(client, fresh_db):
    r = client.get(
        "/me/notifications/unread-count?user_id=ou-nobody",
        headers=_h("ou-nobody"),
    )
    assert r.status_code == 200
    assert r.json()["unread_count"] == 0


def test_mark_read(client, fresh_db):
    ids = _seed(fresh_db, "ou-a", count=2)
    r = client.post(f"/me/notifications/{ids[0]}/read", headers=_h("ou-a"))
    assert r.status_code == 200
    assert r.json()["ok"] is True
    cnt = client.get(
        "/me/notifications/unread-count?user_id=ou-a", headers=_h("ou-a")
    ).json()
    assert cnt["unread_count"] == 1


def test_mark_read_404(client, fresh_db):
    r = client.post("/me/notifications/notif-nope/read", headers=_h("ou-a"))
    assert r.status_code == 404


def test_mark_read_other_users_notification_403(client, fresh_db):
    """v1.0.1 ACL: mark_read 拒标他人通知."""
    ids = _seed(fresh_db, "ou-victim", count=1)
    r = client.post(
        f"/me/notifications/{ids[0]}/read", headers=_h("ou-attacker")
    )
    assert r.status_code == 403


def test_mark_all_read(client, fresh_db):
    _seed(fresh_db, "ou-a", count=4)
    r = client.post(
        "/me/notifications/read-all?user_id=ou-a", headers=_h("ou-a")
    )
    assert r.status_code == 200
    assert r.json()["affected"] == 4
    cnt = client.get(
        "/me/notifications/unread-count?user_id=ou-a", headers=_h("ou-a")
    ).json()
    assert cnt["unread_count"] == 0


def test_mark_all_read_no_unread(client, fresh_db):
    r = client.post(
        "/me/notifications/read-all?user_id=ou-empty", headers=_h("ou-empty")
    )
    assert r.status_code == 200
    assert r.json()["affected"] == 0


def test_list_notifications_isolation_across_users(client, fresh_db):
    """ou-a 通知不应泄漏给 ou-b (T49 §10 SSE 路由)."""
    _seed(fresh_db, "ou-a", count=2)
    _seed(fresh_db, "ou-b", count=3)
    ra = client.get(
        "/me/notifications?user_id=ou-a", headers=_h("ou-a")
    ).json()
    rb = client.get(
        "/me/notifications?user_id=ou-b", headers=_h("ou-b")
    ).json()
    assert len(ra["items"]) == 2
    assert len(rb["items"]) == 3
    # mark-all of a 不影响 b
    client.post(
        "/me/notifications/read-all?user_id=ou-a", headers=_h("ou-a")
    )
    assert (
        client.get(
            "/me/notifications/unread-count?user_id=ou-b", headers=_h("ou-b")
        ).json()["unread_count"]
        == 3
    )
