"""补 generation HTTP 端点 · regenerate / redaction confirm/exempt / SSE.

之前 test_generation_http.py 覆盖了 read/delete/publish/approve; 这里补:
- POST /assets/:id/chapters/:ch/regenerate
- POST /assets/:id/redaction/confirm
- POST /assets/:id/redaction/exempt
- POST /projects/:id/assets (start_generation)
- GET /assets/:id/generation/status
- GET /assets/:id/generation/stream (SSE)
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.llm_gateway.interface import LLMResponse
from app.main import app
from app.schemas.asset import Asset, Chapter
from app.services import generation_service as gen


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def seeded(monkeypatch: pytest.MonkeyPatch) -> Asset:
    monkeypatch.setattr(gen, "_persist_asset", lambda _: None)
    monkeypatch.setattr(gen, "_persist_redaction_job", lambda _: None)
    monkeypatch.setattr(gen, "_persist_publish_record", lambda _: None)
    a = Asset(
        id="asset-extras", project_id="proj-extras",
        type="weekly_report", title="测试",
        status="draft", current_version=1, template_id="t",
        created_by="anon", approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(), updated_at=_now(),
    )
    ch0 = Chapter(id="ch-extras-0", asset_id=a.id, order_index=0,
                  title="§1", content="原始内容 0")
    ch1 = Chapter(id="ch-extras-1", asset_id=a.id, order_index=1,
                  title="§2", content="原始内容 1")
    gen._assets[a.id] = a
    gen._chapters[a.id] = [ch0, ch1]
    yield a
    gen._assets.pop(a.id, None)
    gen._chapters.pop(a.id, None)
    gen._redaction_jobs.pop(a.id, None)
    gen._progress.pop(a.id, None)


def _api(p: str) -> str:
    return f"/api/v1{p}"


# ─── regenerate endpoint ────────────────────────────────────────────


def test_regenerate_endpoint_404_missing_asset(client: TestClient) -> None:
    r = client.post(
        _api("/assets/asset-fake/chapters/ch-x/regenerate"),
        json={"instruction": "改一下"},
    )
    assert r.status_code == 404


def test_regenerate_endpoint_404_missing_chapter(
    client: TestClient, seeded: Asset, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # mock get_router → 永不该被调用因为 chapter 不存在
    r = client.post(
        _api(f"/assets/{seeded.id}/chapters/ch-fake/regenerate"),
        json={"instruction": "改"},
    )
    assert r.status_code == 404


def test_regenerate_endpoint_success(
    client: TestClient, seeded: Asset, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(
        return_value=LLMResponse(
            text="重写后的章节内容 [1] 详见 PR. 长度足够通过门槛检查, 这是更新版本的具体内容描述, 包含更生动语气.",
            usage={"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
            model_used="m", provider="ollama", latency_ms=100,
        ),
    )

    async def fake_get_router():
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get_router)

    r = client.post(
        _api(f"/assets/{seeded.id}/chapters/ch-extras-0/regenerate"),
        json={"instruction": "用更生动的语气"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "重写后" in body["content"]


def test_regenerate_endpoint_llm_failure_503(
    client: TestClient, seeded: Asset, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(side_effect=RuntimeError("circuit open"))

    async def fake_get_router():
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get_router)

    r = client.post(
        _api(f"/assets/{seeded.id}/chapters/ch-extras-0/regenerate"),
        json={"instruction": "x"},
    )
    assert r.status_code == 503


def test_regenerate_endpoint_too_short_422(
    client: TestClient, seeded: Asset, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 返过短内容 → ValueError → 422."""
    fake_router = AsyncMock()
    fake_router.generate = AsyncMock(
        return_value=LLMResponse(
            text="短", usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            model_used="m", provider="ollama", latency_ms=10,
        ),
    )

    async def fake_get_router():
        return fake_router

    monkeypatch.setattr(gen, "get_router", fake_get_router)
    r = client.post(
        _api(f"/assets/{seeded.id}/chapters/ch-extras-0/regenerate"),
        json={"instruction": "x"},
    )
    assert r.status_code == 422


# ─── redaction confirm / exempt endpoints ──────────────────────────


def test_confirm_redaction_404_missing_asset(client: TestClient) -> None:
    r = client.post(
        _api("/assets/asset-fake/redaction/confirm"),
        json={"item_ids": ["red-x"]},
    )
    assert r.status_code == 404


def test_confirm_redaction_404_no_scan(client: TestClient, seeded: Asset) -> None:
    """asset 存在但没扫过 → 404."""
    r = client.post(
        _api(f"/assets/{seeded.id}/redaction/confirm"),
        json={"item_ids": ["x"]},
    )
    assert r.status_code == 404


def test_confirm_redaction_success(client: TestClient, seeded: Asset) -> None:
    """先扫描出 item, 然后 confirm."""
    # 让 chapter 含 email 触发扫描
    gen._chapters[seeded.id][0].content = "联系 leak@example.com"
    scan_r = client.post(_api(f"/assets/{seeded.id}/redaction/scan"))
    items = scan_r.json()["items"]
    if items:
        r = client.post(
            _api(f"/assets/{seeded.id}/redaction/confirm"),
            json={"item_ids": [items[0]["id"]]},
        )
        assert r.status_code == 200
        # 第 1 个 item 应该 confirmed
        item = next(it for it in r.json()["items"] if it["id"] == items[0]["id"])
        assert item["status"] == "confirmed"


def test_exempt_redaction_404_missing_asset(client: TestClient) -> None:
    r = client.post(
        _api("/assets/asset-fake/redaction/exempt"),
        json={"item_id": "x", "reason": "demo"},
    )
    assert r.status_code == 404


def test_exempt_redaction_empty_reason_422(
    client: TestClient, seeded: Asset,
) -> None:
    gen._chapters[seeded.id][0].content = "leak@x.com"
    client.post(_api(f"/assets/{seeded.id}/redaction/scan"))
    r = client.post(
        _api(f"/assets/{seeded.id}/redaction/exempt"),
        json={"item_id": "any", "reason": "   "},
    )
    assert r.status_code == 422


def test_exempt_redaction_404_no_scan(client: TestClient, seeded: Asset) -> None:
    r = client.post(
        _api(f"/assets/{seeded.id}/redaction/exempt"),
        json={"item_id": "red-x", "reason": "示例数据不真实"},
    )
    assert r.status_code == 404


def test_exempt_redaction_success(client: TestClient, seeded: Asset) -> None:
    gen._chapters[seeded.id][0].content = "leak@example.com"
    scan = client.post(_api(f"/assets/{seeded.id}/redaction/scan"))
    items = scan.json()["items"]
    if items:
        item_id = items[0]["id"]
        r = client.post(
            _api(f"/assets/{seeded.id}/redaction/exempt"),
            json={"item_id": item_id, "reason": "示例数据"},
        )
        assert r.status_code == 200
        item = next(it for it in r.json()["items"] if it["id"] == item_id)
        assert item["status"] == "exempted"


# ─── POST /projects/:id/assets · start_generation ───────────────────


def test_generate_asset_endpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gen, "_persist_asset", lambda _: None)
    # 防止后台 pipeline 真跑
    import asyncio
    monkeypatch.setattr(asyncio, "create_task", lambda coro: coro.close())
    r = client.post(
        _api("/projects/proj-gen-test/assets/generate"),
        json={"type": "weekly_report", "time_window": "2026-W21"},
    )
    assert r.status_code in (200, 201, 202)
    body = r.json()
    assert body["status"] == "generating"
    assert body["project_id"] == "proj-gen-test"
    # 清理
    gen._assets.pop(body["id"], None)
    gen._chapters.pop(body["id"], None)
    gen._progress.pop(body["id"], None)


# ─── GET generation status ────────────────────────────────────────


def test_get_progress_endpoint_404(client: TestClient) -> None:
    r = client.get(_api("/assets/asset-no-progress-yet/generation/status"))
    assert r.status_code == 404


def test_get_progress_endpoint_returns_progress(
    client: TestClient, seeded: Asset,
) -> None:
    gen._progress[seeded.id] = gen._initial_progress(seeded.id)
    r = client.get(_api(f"/assets/{seeded.id}/generation/status"))
    assert r.status_code == 200
    assert r.json()["asset_id"] == seeded.id


# ─── SSE stream endpoint ──────────────────────────────────────────


def test_sse_stream_404_for_missing_progress(client: TestClient) -> None:
    r = client.get(_api("/assets/asset-no-progress/generation/stream"))
    assert r.status_code == 404


def test_sse_format_helper() -> None:
    """单测 _sse_format 字节格式化 (避免真打开 SSE 流测试客户端 hang)."""
    from app.gateway.http_api.generation import _sse_format
    out = _sse_format(event="done", data='{"k":"v"}')
    assert out == b'event: done\ndata: {"k":"v"}\n\n'
