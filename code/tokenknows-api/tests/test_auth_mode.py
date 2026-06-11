"""v2.1 · AUTH_MODE 门禁 (require_auth_if_required) + 启动期安全校验."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import security_checks
from app.config import settings as settings_module
from app.config.settings import DEV_DEFAULT_JWT_SECRET
from app.gateway.http_api import api_router
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.services.auth import pat_service

PROJECT_ID = "proj-authmode-001"


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    return s


@pytest.fixture
def client(fresh_db) -> TestClient:
    """真实 api_router (含 __init__.py 的 _auth_gate 接线), 不走 lifespan."""
    app = FastAPI()
    app.include_router(api_router)
    return TestClient(app)


# ─── auth_mode=open (默认, backward-compat) ───────────────


def test_open_mode_unauthenticated_events_200(client, monkeypatch):
    monkeypatch.setattr(settings_module.get_settings(), "auth_mode", "open")
    r = client.get(f"/projects/{PROJECT_ID}/events")
    assert r.status_code == 200


# ─── auth_mode=required ───────────────────────────────────


def test_required_mode_unauthenticated_401(client, monkeypatch):
    monkeypatch.setattr(settings_module.get_settings(), "auth_mode", "required")
    r = client.get(f"/projects/{PROJECT_ID}/events")
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_required_mode_valid_pat_200(client, monkeypatch):
    monkeypatch.setattr(settings_module.get_settings(), "auth_mode", "required")
    plaintext, _ = pat_service.create_token(user_id="user-pat", name="mcp")
    r = client.get(
        f"/projects/{PROJECT_ID}/events",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r.status_code == 200


def test_required_mode_x_user_id_only_401(client, monkeypatch):
    """required 模式下 X-User-Id (trust-on-faith) 不算认证."""
    monkeypatch.setattr(settings_module.get_settings(), "auth_mode", "required")
    r = client.get(
        f"/projects/{PROJECT_ID}/events",
        headers={"X-User-Id": "user-spoofed"},
    )
    assert r.status_code == 401


def test_required_mode_revoked_pat_401(client, monkeypatch):
    monkeypatch.setattr(settings_module.get_settings(), "auth_mode", "required")
    plaintext, token = pat_service.create_token(user_id="user-pat", name="t")
    assert pat_service.revoke_token(user_id="user-pat", token_id=token.id)
    r = client.get(
        f"/projects/{PROJECT_ID}/events",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r.status_code == 401


# ─── validate_security (启动期门禁) ───────────────────────


def test_validate_security_raises_nonlocal_default_secret(monkeypatch):
    s = settings_module.get_settings()
    monkeypatch.setattr(s, "environment", "production")
    monkeypatch.setattr(s, "jwt_secret_key", DEV_DEFAULT_JWT_SECRET)
    with pytest.raises(RuntimeError):
        security_checks.validate_security(s)


def test_validate_security_passes_nonlocal_custom_secret(monkeypatch):
    s = settings_module.get_settings()
    monkeypatch.setattr(s, "environment", "production")
    monkeypatch.setattr(s, "jwt_secret_key", "a-strong-rotated-secret-123")
    # 不抛即通过
    security_checks.validate_security(s)


def test_validate_security_warns_not_raises_for_local(monkeypatch):
    s = settings_module.get_settings()
    monkeypatch.setattr(s, "environment", "local")
    monkeypatch.setattr(s, "jwt_secret_key", DEV_DEFAULT_JWT_SECRET)

    warned: list[str] = []

    class _StubLogger:
        def warning(self, event: str, **kwargs) -> None:
            warned.append(event)

    monkeypatch.setattr(security_checks, "logger", _StubLogger())
    security_checks.validate_security(s)  # 不抛
    assert warned == ["jwt_secret_is_dev_default"]


def test_open_mode_pat_bearer_still_touches_last_used(
    client, fresh_db, monkeypatch
):
    """open 模式不强制鉴权, 但带 PAT 的请求仍要更新 last_used_at —
    Web 面板的"插件已连上"信号在默认部署下才真实."""
    monkeypatch.setattr(settings_module.get_settings(), "auth_mode", "open")
    plaintext, token = pat_service.create_token(user_id="user-open", name="t")
    assert token.last_used_at is None
    r = client.get(
        f"/projects/{PROJECT_ID}/events",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r.status_code == 200
    raw = fresh_db.get_api_token_by_hash(token.token_hash)
    assert raw is not None and raw["last_used_at"] is not None
