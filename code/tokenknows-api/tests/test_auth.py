"""T74+T75 · JWT auth endpoints + session resolver."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.http_api.auth import router as auth_router
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.services.auth import token as auth_token
from app.services.auth import user_service


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
    app.include_router(auth_router)
    return TestClient(app)


# ─── password hash ────────────────────────────────────────


def test_hash_and_verify_password_ok():
    h = auth_token.hash_password("hello-secret-123")
    assert auth_token.verify_password("hello-secret-123", h) is True
    assert auth_token.verify_password("wrong-pass", h) is False


def test_verify_password_handles_invalid_hash():
    """传无效 hash → False (不抛)."""
    assert auth_token.verify_password("any", "not-a-bcrypt-hash") is False


# ─── JWT issue / decode ──────────────────────────────────


def test_issue_and_decode_token_roundtrip():
    token = auth_token.issue_access_token("user-1")
    payload = auth_token.decode_token(token)
    assert payload["sub"] == "user-1"
    assert payload["type"] == "access"
    assert "exp" in payload


def test_decode_token_invalid_raises():
    with pytest.raises(auth_token.AuthError):
        auth_token.decode_token("invalid.token.here")


def test_decode_token_tampered_raises():
    token = auth_token.issue_access_token("user-1")
    tampered = token[:-3] + "AAA"
    with pytest.raises(auth_token.AuthError):
        auth_token.decode_token(tampered)


def test_decode_expired_token_raises(monkeypatch):
    from app.config import settings as s
    # 设 TTL = 0 (秒级过期)
    monkeypatch.setattr(s.get_settings(), "jwt_access_token_ttl_minutes", 0)
    token = auth_token.issue_access_token("user-x")
    # 等一秒确保 exp 过去
    import time
    time.sleep(1.1)
    with pytest.raises(auth_token.AuthError):
        auth_token.decode_token(token)


def test_get_user_id_from_token():
    token = auth_token.issue_access_token("user-42")
    assert auth_token.get_user_id_from_token(token) == "user-42"


# ─── user_service ────────────────────────────────────────


def test_register_user_ok(fresh_db):
    user = user_service.register(
        email="alice@example.com",
        password="password-123",
        display_name="Alice",
    )
    assert user.id.startswith("user-")
    assert user.email == "alice@example.com"
    # 密码应是 hash, 不是明文
    assert user.password_hash != "password-123"


def test_register_email_normalized(fresh_db):
    """email 应小写存储."""
    user = user_service.register(
        email="ALICE@EXAMPLE.COM",
        password="pwd-123456",
        display_name="A",
    )
    assert user.email == "alice@example.com"


def test_register_duplicate_email_raises(fresh_db):
    user_service.register(
        email="a@b.com", password="pwd-12345", display_name="A",
    )
    with pytest.raises(user_service.UserAlreadyExists):
        user_service.register(
            email="a@b.com", password="other-pass-78", display_name="B",
        )


def test_login_ok(fresh_db):
    user_service.register(
        email="b@c.com", password="my-secret-pw", display_name="B",
    )
    user = user_service.login(email="b@c.com", password="my-secret-pw")
    assert user.email == "b@c.com"
    assert user.last_login_at is not None


def test_login_wrong_password_raises(fresh_db):
    user_service.register(
        email="x@y.com", password="correct-pass", display_name="X",
    )
    with pytest.raises(user_service.InvalidCredentials):
        user_service.login(email="x@y.com", password="wrong")


def test_login_unknown_email_raises(fresh_db):
    """unknown email 同样返 InvalidCredentials (防 enumeration)."""
    with pytest.raises(user_service.InvalidCredentials):
        user_service.login(email="nope@example.com", password="x")


# ─── /auth/register endpoint ──────────────────────────────


def test_register_endpoint_happy(client):
    r = client.post(
        "/auth/register",
        json={
            "email": "alice@example.com",
            "password": "very-secret-pw",
            "display_name": "Alice",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "alice@example.com"
    assert "password_hash" not in body["user"]


def test_register_endpoint_409_duplicate(client):
    client.post(
        "/auth/register",
        json={
            "email": "x@y.com", "password": "pwd-12345",
            "display_name": "X",
        },
    )
    r = client.post(
        "/auth/register",
        json={
            "email": "x@y.com", "password": "another-pwd",
            "display_name": "Y",
        },
    )
    assert r.status_code == 409


def test_register_endpoint_422_short_password(client):
    """password < 8 chars → 422."""
    r = client.post(
        "/auth/register",
        json={
            "email": "a@b.com", "password": "short",
            "display_name": "A",
        },
    )
    assert r.status_code == 422


def test_register_endpoint_422_invalid_email(client):
    r = client.post(
        "/auth/register",
        json={
            "email": "not-an-email", "password": "ok-password-1",
            "display_name": "A",
        },
    )
    assert r.status_code == 422


# ─── /auth/login endpoint ─────────────────────────────────


def test_login_endpoint_happy(client):
    client.post(
        "/auth/register",
        json={
            "email": "c@d.com", "password": "secret-pw-789",
            "display_name": "C",
        },
    )
    r = client.post(
        "/auth/login",
        json={"email": "c@d.com", "password": "secret-pw-789"},
    )
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_endpoint_401_wrong_password(client):
    client.post(
        "/auth/register",
        json={
            "email": "e@f.com", "password": "correct-pw-12",
            "display_name": "E",
        },
    )
    r = client.post(
        "/auth/login",
        json={"email": "e@f.com", "password": "wrong-pw"},
    )
    assert r.status_code == 401


def test_login_endpoint_401_unknown_user(client):
    r = client.post(
        "/auth/login",
        json={"email": "nope@x.com", "password": "any"},
    )
    assert r.status_code == 401


# ─── /auth/me endpoint ────────────────────────────────────


def test_get_me_with_jwt_bearer(client):
    reg = client.post(
        "/auth/register",
        json={
            "email": "g@h.com", "password": "pw-12345678",
            "display_name": "G",
        },
    )
    token = reg.json()["access_token"]
    r = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    assert r.json()["email"] == "g@h.com"


def test_get_me_with_x_user_id_backward_compat(client):
    """无 JWT 但有 X-User-Id 也应通过 (v0.9 backward-compat)."""
    reg = client.post(
        "/auth/register",
        json={
            "email": "i@j.com", "password": "pw-12345678",
            "display_name": "I",
        },
    )
    user_id = reg.json()["user"]["id"]
    r = client.get(
        "/auth/me", headers={"X-User-Id": user_id}
    )
    assert r.status_code == 200
    assert r.json()["email"] == "i@j.com"


def test_get_me_no_auth_401(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_get_me_invalid_token_401(client):
    """无效 JWT → 401 (fall through to no-session)."""
    r = client.get(
        "/auth/me", headers={"Authorization": "Bearer invalid.jwt.here"}
    )
    assert r.status_code == 401


def test_jwt_preferred_over_x_user_id(client):
    """同时传 JWT 和 X-User-Id, 优先用 JWT 解的 user."""
    reg1 = client.post(
        "/auth/register",
        json={
            "email": "p@q.com", "password": "pw-12345678",
            "display_name": "P",
        },
    )
    token = reg1.json()["access_token"]
    user_p_id = reg1.json()["user"]["id"]

    reg2 = client.post(
        "/auth/register",
        json={
            "email": "r@s.com", "password": "pw-12345678",
            "display_name": "R",
        },
    )
    user_r_id = reg2.json()["user"]["id"]

    # JWT 是 P, X-User-Id 谎称 R → 应解出 P (JWT 优先)
    r = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
            "X-User-Id": user_r_id,  # 攻击企图
        },
    )
    assert r.status_code == 200
    assert r.json()["id"] == user_p_id  # 应该是 P
