"""T49+T51 · /me/notifications HTTP endpoints."""

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
    r = client.get("/me/notifications?user_id=ou-a")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert body["unread_count"] == 2
    # 验 user filter 严格
    for n in body["items"]:
        assert n["user_id"] == "ou-a"


def test_list_notifications_unread_only(client, fresh_db):
    _seed(fresh_db, "ou-a", count=2, read=False)
    _seed(fresh_db, "ou-a", count=1, read=True)  # 实际是 3 个里 1 个已读
    # 上面会重写覆盖, 重新清晰构造:
    fresh_db._exec("DELETE FROM notifications", ())
    _seed(fresh_db, "ou-a", count=2, read=False)
    # 手工建一条已读
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
    r = client.get("/me/notifications?user_id=ou-a&unread_only=true")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert body["unread_count"] == 2


def test_list_notifications_limit_bounds(client, fresh_db):
    _seed(fresh_db, "ou-a", count=5)
    r = client.get("/me/notifications?user_id=ou-a&limit=3")
    assert r.status_code == 200
    assert len(r.json()["items"]) == 3


def test_list_notifications_user_id_required(client):
    r = client.get("/me/notifications")
    assert r.status_code == 422  # Pydantic 强制 user_id


def test_unread_count(client, fresh_db):
    _seed(fresh_db, "ou-a", count=3)
    r = client.get("/me/notifications/unread-count?user_id=ou-a")
    assert r.status_code == 200
    assert r.json()["unread_count"] == 3


def test_unread_count_zero_for_unknown_user(client, fresh_db):
    r = client.get("/me/notifications/unread-count?user_id=ou-nobody")
    assert r.status_code == 200
    assert r.json()["unread_count"] == 0


def test_mark_read(client, fresh_db):
    ids = _seed(fresh_db, "ou-a", count=2)
    r = client.post(f"/me/notifications/{ids[0]}/read")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # 再查未读应为 1
    cnt = client.get("/me/notifications/unread-count?user_id=ou-a").json()
    assert cnt["unread_count"] == 1


def test_mark_read_404(client):
    r = client.post("/me/notifications/notif-nope/read")
    assert r.status_code == 404


def test_mark_all_read(client, fresh_db):
    _seed(fresh_db, "ou-a", count=4)
    r = client.post("/me/notifications/read-all?user_id=ou-a")
    assert r.status_code == 200
    assert r.json()["affected"] == 4
    cnt = client.get("/me/notifications/unread-count?user_id=ou-a").json()
    assert cnt["unread_count"] == 0


def test_mark_all_read_no_unread(client, fresh_db):
    r = client.post("/me/notifications/read-all?user_id=ou-empty")
    assert r.status_code == 200
    assert r.json()["affected"] == 0


def test_list_notifications_isolation_across_users(client, fresh_db):
    """ou-a 通知不应泄漏给 ou-b (隐私 — T49 §10 SSE 路由)."""
    _seed(fresh_db, "ou-a", count=2)
    _seed(fresh_db, "ou-b", count=3)
    ra = client.get("/me/notifications?user_id=ou-a").json()
    rb = client.get("/me/notifications?user_id=ou-b").json()
    assert len(ra["items"]) == 2
    assert len(rb["items"]) == 3
    # mark-all of a 不影响 b
    client.post("/me/notifications/read-all?user_id=ou-a")
    assert client.get("/me/notifications/unread-count?user_id=ou-b").json()["unread_count"] == 3
