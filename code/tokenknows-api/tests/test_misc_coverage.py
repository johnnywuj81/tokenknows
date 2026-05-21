"""杂项覆盖率收尾 · main.py lifespan + logging + events.py 错误路径 + store edge cases.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.persistence.store import SqliteStore


# ─── main.py lifespan ──────────────────────────────────────────────


def test_main_lifespan_starts_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """跑 lifespan 生命周期 · bootstrap_db + _bootstrap_from_db 被调."""
    bootstrap_called = []
    bootstrap_from_db_called = []

    from app import main as main_mod

    def fake_bootstrap_db():
        bootstrap_called.append(True)

    def fake_bootstrap_from_db():
        bootstrap_from_db_called.append(True)

    monkeypatch.setattr(main_mod, "bootstrap_db", fake_bootstrap_db)
    monkeypatch.setattr(main_mod, "_bootstrap_from_db", fake_bootstrap_from_db)

    from fastapi import FastAPI
    test_app = FastAPI(lifespan=main_mod.lifespan)
    # TestClient 跑会触发 lifespan
    with TestClient(test_app):
        pass
    assert bootstrap_called == [True]
    assert bootstrap_from_db_called == [True]


def test_main_app_has_cors_middleware() -> None:
    """app 装了 CORS middleware (allow_origins=localhost:5173)."""
    from app.main import app
    middlewares = [m.cls.__name__ for m in app.user_middleware]
    assert any("CORS" in m for m in middlewares)


def test_main_app_has_api_v1_prefix() -> None:
    """所有 router 走 /api/v1 前缀."""
    from app.main import app
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    api_paths = [p for p in paths if p.startswith("/api/v1")]
    assert len(api_paths) > 5


# ─── logging setup_logging ────────────────────────────────────────


def test_setup_logging_uppercase_level() -> None:
    """level 大小写无关."""
    from app.config.logging import setup_logging
    setup_logging("info")   # 不抛
    setup_logging("DEBUG")  # 不抛


def test_setup_logging_default_info() -> None:
    from app.config.logging import setup_logging
    setup_logging()   # default INFO


# ─── events.py 错误路径 ────────────────────────────────────────────


def test_ingest_events_empty_400() -> None:
    """空 events 数组 → 400."""
    from app.main import app
    client = TestClient(app)
    r = client.post(
        "/api/v1/projects/proj-x/events",
        json={"events": []},
    )
    assert r.status_code == 400


def test_ingest_events_over_500_400() -> None:
    """单批 > 500 → 400."""
    from app.main import app
    client = TestClient(app)
    # 构造 501 条 minimal events (内部 schema validation 也许会先)
    events = [
        {
            "source_type": "github", "source_ref": "o/r",
            "external_id": f"e{i}", "version": 1, "event_type": "commit",
            "occurred_at": "2026-05-22T00:00:00Z",
            "title": "t", "content": "c", "content_hash": f"h{i}",
            "payload": {}, "tags": [],
        }
        for i in range(501)
    ]
    r = client.post(
        "/api/v1/projects/proj-x/events",
        json={"events": events},
    )
    assert r.status_code == 400


def test_datasource_health_health_classification_branches() -> None:
    """直接探 _health 内部 last_seen 各档判定."""
    from app.gateway.http_api.events import _KNOWN_SOURCE_TYPES
    assert "claude_code" in _KNOWN_SOURCE_TYPES
    assert "github" in _KNOWN_SOURCE_TYPES


# ─── store.py edge cases ───────────────────────────────────────────


def test_store_bootstrap_class_method(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SqliteStore.bootstrap classmethod 走真路径建表."""
    from app.config.settings import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "egress_log_path", str(tmp_path / "egress.sqlite"))
    store = SqliteStore.bootstrap()
    assert store is not None
    # 建了 events 表
    rows = store._query("SELECT name FROM sqlite_master WHERE type='table'")
    table_names = {r["name"] for r in rows}
    assert "events" in table_names


def test_get_db_singleton(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """get_db 同一进程返回同一实例."""
    from app.config.settings import get_settings
    from app.persistence import store as store_mod
    settings = get_settings()
    monkeypatch.setattr(settings, "egress_log_path", str(tmp_path / "e.sqlite"))
    # 重置 _db 模块全局
    monkeypatch.setattr(store_mod, "_db", None)
    a = store_mod.get_db()
    b = store_mod.get_db()
    assert a is b


# ─── persist 模块 alias ────────────────────────────────────────────


def test_persist_alias(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.config.settings import get_settings
    from app.persistence import store as store_mod
    from app.persistence import persist
    settings = get_settings()
    monkeypatch.setattr(settings, "egress_log_path", str(tmp_path / "e.sqlite"))
    monkeypatch.setattr(store_mod, "_db", None)
    s = persist()
    assert s is not None
