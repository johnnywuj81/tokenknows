"""v2.1 · PAT (Personal Access Token) endpoints + pat_service."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.http_api.auth import router as auth_router
from app.gateway.http_api.tokens import router as tokens_router
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.services.auth import pat_service


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
    app.include_router(tokens_router)
    return TestClient(app)


def _register_user(
    client: TestClient, email: str = "alice@example.com"
) -> tuple[str, dict[str, str]]:
    """注册真实账户, 返回 (user_id, JWT Bearer headers).

    /me/tokens 仅认 Bearer (require_verified_user_id) — 伪造的
    X-User-Id 不能签发长期凭证, 所以测试统一用注册返回的 JWT.
    """
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "very-secret-pw",
            "display_name": "Alice",
        },
    )
    assert r.status_code == 201
    body = r.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    return body["user"]["id"], headers


# ─── POST /me/tokens ──────────────────────────────────────


def test_create_token_returns_tkk_plaintext_201(client):
    _, auth = _register_user(client)
    r = client.post("/me/tokens", json={"name": "my mcp token"}, headers=auth)
    assert r.status_code == 201
    body = r.json()
    assert body["token"].startswith("tkk_")
    assert body["item"]["name"] == "my mcp token"
    assert body["item"]["token_prefix"] == body["token"][:12]
    assert body["item"]["last_used_at"] is None


def test_create_token_stored_hash_differs_from_plaintext(client, fresh_db):
    user_id, auth = _register_user(client)
    r = client.post("/me/tokens", json={"name": "t1"}, headers=auth)
    plaintext = r.json()["token"]
    raws = fresh_db.list_api_tokens_for_user(user_id)
    assert len(raws) == 1
    assert raws[0]["token_hash"] != plaintext
    assert plaintext not in raws[0]["token_hash"]


def test_create_token_no_auth_401(client):
    r = client.post("/me/tokens", json={"name": "t"})
    assert r.status_code == 401


def test_create_token_x_user_id_only_401(client):
    """X-User-Id 是 trust-on-faith header, 不能用来签发长期凭证 (PAT)."""
    user_id, _ = _register_user(client)
    r = client.post(
        "/me/tokens",
        json={"name": "spoofed"},
        headers={"X-User-Id": user_id},
    )
    assert r.status_code == 401


def test_create_token_over_limit_400(client, monkeypatch):
    _, auth = _register_user(client)
    monkeypatch.setattr(pat_service, "MAX_ACTIVE_TOKENS_PER_USER", 2)
    for i in range(2):
        assert (
            client.post(
                "/me/tokens", json={"name": f"t{i}"}, headers=auth
            ).status_code
            == 201
        )
    r = client.post("/me/tokens", json={"name": "t-over"}, headers=auth)
    assert r.status_code == 400
    assert "limit" in r.json()["detail"]


# ─── GET /me/tokens ───────────────────────────────────────


def test_list_tokens_leaks_neither_hash_nor_plaintext(client):
    _, auth = _register_user(client)
    created = client.post("/me/tokens", json={"name": "t1"}, headers=auth)
    plaintext = created.json()["token"]
    r = client.get("/me/tokens", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert "token_hash" not in items[0]
    assert "token" not in items[0]
    # 整个响应体里不出现明文
    assert plaintext not in r.text


# ─── PAT 作为 Bearer 认证 ─────────────────────────────────


def test_get_me_with_pat_bearer_200(client):
    user_id, auth = _register_user(client)
    created = client.post("/me/tokens", json={"name": "mcp"}, headers=auth)
    pat = created.json()["token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {pat}"})
    assert r.status_code == 200
    assert r.json()["id"] == user_id


def test_pat_bearer_can_manage_tokens(client):
    """PAT 本身也是合法 Bearer — 可用来列/撤 token (Bearer-only 门禁)."""
    _, auth = _register_user(client)
    created = client.post("/me/tokens", json={"name": "mcp"}, headers=auth)
    pat = created.json()["token"]
    r = client.get(
        "/me/tokens", headers={"Authorization": f"Bearer {pat}"}
    )
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1


# ─── DELETE /me/tokens/{id} (撤销) ────────────────────────


def test_revoke_204_then_same_pat_401(client):
    _, auth = _register_user(client)
    created = client.post("/me/tokens", json={"name": "to-revoke"}, headers=auth)
    pat = created.json()["token"]
    token_id = created.json()["item"]["id"]

    r = client.delete(f"/me/tokens/{token_id}", headers=auth)
    assert r.status_code == 204
    # 撤销后同一 PAT 不再可用
    r2 = client.get("/auth/me", headers={"Authorization": f"Bearer {pat}"})
    assert r2.status_code == 401
    # 列表里也不再出现
    r3 = client.get("/me/tokens", headers=auth)
    assert r3.json()["items"] == []


def test_revoke_other_users_token_404(client):
    _, owner_auth = _register_user(client, email="owner@example.com")
    _, attacker_auth = _register_user(client, email="attacker@example.com")
    created = client.post(
        "/me/tokens", json={"name": "owner-token"}, headers=owner_auth
    )
    token_id = created.json()["item"]["id"]
    r = client.delete(f"/me/tokens/{token_id}", headers=attacker_auth)
    assert r.status_code == 404
    # owner 的 token 仍有效
    r2 = client.get("/me/tokens", headers=owner_auth)
    assert len(r2.json()["items"]) == 1


def test_revoke_unknown_token_404(client):
    _, auth = _register_user(client)
    r = client.delete("/me/tokens/pat-nonexistent", headers=auth)
    assert r.status_code == 404


# ─── pat_service 直测 ─────────────────────────────────────


def test_verify_garbage_tkk_token_returns_none(fresh_db):
    assert pat_service.verify_token("tkk_not-a-real-token-at-all") is None


def test_verify_non_tkk_prefix_returns_none(fresh_db):
    assert pat_service.verify_token("jwt.looking.token") is None
    assert pat_service.verify_token("") is None


def test_verify_roundtrip_returns_user_id(fresh_db):
    plaintext, token = pat_service.create_token(user_id="user-abc", name="t")
    assert token.token_hash != plaintext
    assert pat_service.verify_token(plaintext) == "user-abc"


def test_last_used_at_updated_after_verify(fresh_db):
    plaintext, token = pat_service.create_token(user_id="user-abc", name="t")
    assert token.last_used_at is None
    assert pat_service.verify_token(plaintext) == "user-abc"
    raw = fresh_db.get_api_token_by_hash(token.token_hash)
    assert raw is not None
    assert raw["last_used_at"] is not None


def test_create_token_limit_service_layer(fresh_db, monkeypatch):
    monkeypatch.setattr(pat_service, "MAX_ACTIVE_TOKENS_PER_USER", 1)
    pat_service.create_token(user_id="user-x", name="t1")
    with pytest.raises(pat_service.TokenLimitError):
        pat_service.create_token(user_id="user-x", name="t2")
    # 撤销后可再建
    [tok] = pat_service.list_tokens("user-x")
    assert pat_service.revoke_token(user_id="user-x", token_id=tok.id)
    pat_service.create_token(user_id="user-x", name="t3")
