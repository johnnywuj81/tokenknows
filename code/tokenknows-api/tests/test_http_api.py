"""HTTP API 端点 smoke test · FastAPI TestClient.

只测端点契约 (status code / response shape), 不测业务逻辑深处.
跑得快, 不依赖 ollama / 真 LLM. SQLite 走真持久化 (state.sqlite 共享).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


PROJECT_ID = "proj-demo-001"


# ─── liveness ────────────────────────────────────────────────────────


def test_healthz_returns_200(client: TestClient) -> None:
    r = client.get("/api/v1/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") in ("ok", "healthy")


def test_readyz_returns_200(client: TestClient) -> None:
    r = client.get("/api/v1/readyz")
    # 200 ready / 503 starting up; 都接受
    assert r.status_code in (200, 503)


# ─── /projects/:id/datasources/health ────────────────────────────────


def test_datasource_health_contract(client: TestClient) -> None:
    """端点存在 + 返回 dict 含 items 数组 + 6 个固定源 (T136 加 claude_cowork)."""
    r = client.get(f"/api/v1/projects/{PROJECT_ID}/datasources/health")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "window_days" in body
    assert "total_active" in body
    assert "total_events_all" in body
    # 6 个固定源都返回 (即使 event_count=0)
    types = {it["source_type"] for it in body["items"]}
    assert {
        "claude_code",
        "claude_cowork",
        "github",
        "cursor",
        "vscode",
        "local_file",
    }.issubset(types)


def test_datasource_health_window_param(client: TestClient) -> None:
    """window_days 可调."""
    r = client.get(
        f"/api/v1/projects/{PROJECT_ID}/datasources/health",
        params={"window_days": 7},
    )
    assert r.status_code == 200
    assert r.json()["window_days"] == 7


def test_datasource_health_each_item_has_required_fields(client: TestClient) -> None:
    r = client.get(f"/api/v1/projects/{PROJECT_ID}/datasources/health")
    assert r.status_code == 200
    for item in r.json()["items"]:
        for key in ("source_type", "event_count", "total_events", "health"):
            assert key in item, f"missing {key} in {item}"
        assert item["health"] in ("active", "stale", "cold", "inactive")


def test_datasource_health_unknown_project(client: TestClient) -> None:
    """陌生 project_id 也不 500, 返回 6 个 inactive 源 (T136 加 claude_cowork)."""
    r = client.get("/api/v1/projects/proj-nonexistent-xxx/datasources/health")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 6
    assert all(it["health"] == "inactive" for it in body["items"])
    assert body["total_events_all"] == 0


# ─── /projects/:id/stats ─────────────────────────────────────────────


def test_stats_contract(client: TestClient) -> None:
    r = client.get(f"/api/v1/projects/{PROJECT_ID}/stats")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "events_this_week",
        "assets_pending_review",
        "datasources_total",
        "datasources_healthy",
    ):
        assert key in body
    # 数字字段应该 ≥ 0
    assert body["events_this_week"] >= 0
    assert body["assets_pending_review"] >= 0


# ─── /projects/:id/events ────────────────────────────────────────────


def test_events_list_contract(client: TestClient) -> None:
    """事件列表分页响应."""
    r = client.get(
        f"/api/v1/projects/{PROJECT_ID}/events",
        params={"limit": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert "meta" in body
    assert "total" in body["meta"]
    assert "has_more" in body["meta"]
    assert isinstance(body["data"], list)
    assert len(body["data"]) <= 5


def test_events_filter_by_source_type(client: TestClient) -> None:
    """source_type 过滤生效."""
    r = client.get(
        f"/api/v1/projects/{PROJECT_ID}/events",
        params={"source_type": "claude_code", "limit": 3},
    )
    assert r.status_code == 200
    for ev in r.json()["data"]:
        assert ev["source_type"] == "claude_code"


# ─── /events/:id ─────────────────────────────────────────────────────


def test_event_detail_404_on_missing(client: TestClient) -> None:
    r = client.get("/api/v1/events/ev-totally-fake-9999")
    assert r.status_code == 404


def test_event_detail_returns_full_event(client: TestClient) -> None:
    """先列, 再用第一个 id 取详情, 字段齐全."""
    list_r = client.get(
        f"/api/v1/projects/{PROJECT_ID}/events",
        params={"limit": 1},
    )
    data: list[dict[str, Any]] = list_r.json()["data"]
    if not data:
        pytest.skip("no events in proj-demo-001 to test detail")
    ev_id = data[0]["id"]
    r = client.get(f"/api/v1/events/{ev_id}")
    assert r.status_code == 200
    body = r.json()
    # 必需字段
    for key in ("id", "project_id", "source_type", "event_type", "occurred_at", "content"):
        assert key in body
    assert body["id"] == ev_id
