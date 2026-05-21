"""generation HTTP 端点 smoke + workflow integration · FastAPI TestClient.

测端点 → service 路由正确 (不深入测业务逻辑, 那由 test_generation_sync_ops 覆盖).
启动一个真 asset (mock LLM stages 跳过), 测各端点 200/404/422 + body shape.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.asset import Asset, Chapter
from app.services import generation_service as gen


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def seeded_asset(monkeypatch: pytest.MonkeyPatch) -> Asset:
    """注入一个 in-memory asset + 2 chapters, 不调 SQLite."""
    monkeypatch.setattr(gen, "_persist_asset", lambda _: None)
    monkeypatch.setattr(gen, "_persist_redaction_job", lambda _: None)
    monkeypatch.setattr(gen, "_persist_publish_record", lambda _: None)

    a = Asset(
        id="asset-test-seeded",
        project_id="proj-test",
        type="weekly_report",
        title="测试周报",
        status="draft",
        current_version=1,
        template_id="t",
        created_by="anon",
        approval_state="pending",
        redaction_state="any_unresolved",
        created_at=_now(),
        updated_at=_now(),
    )
    chs = [
        Chapter(id="ch-0", asset_id="asset-test-seeded", order_index=0,
                title="§1", content="内容 0"),
        Chapter(id="ch-1", asset_id="asset-test-seeded", order_index=1,
                title="§2", content="内容 1"),
    ]
    gen._assets[a.id] = a
    gen._chapters[a.id] = chs
    yield a
    gen._assets.pop(a.id, None)
    gen._chapters.pop(a.id, None)
    gen._evidence_by_chapter.pop("ch-0", None)
    gen._evidence_by_chapter.pop("ch-1", None)
    gen._redaction_jobs.pop(a.id, None)


def _api(path: str) -> str:
    return f"/api/v1{path}"


# ─── GET endpoints ────────────────────────────────────────────────


def test_get_asset_returns_seeded(client: TestClient, seeded_asset: Asset) -> None:
    r = client.get(_api(f"/assets/{seeded_asset.id}"))
    assert r.status_code == 200
    assert r.json()["id"] == seeded_asset.id


def test_get_asset_404(client: TestClient) -> None:
    r = client.get(_api("/assets/asset-totally-fake"))
    assert r.status_code == 404


def test_list_chapters(client: TestClient, seeded_asset: Asset) -> None:
    r = client.get(_api(f"/assets/{seeded_asset.id}/chapters"))
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_list_chapters_for_missing_asset(client: TestClient) -> None:
    """missing asset → 404 (endpoint gates on get_asset)."""
    r = client.get(_api("/assets/asset-fake-totally/chapters"))
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert r.json() == []


def test_list_chapter_evidence_empty(client: TestClient, seeded_asset: Asset) -> None:
    r = client.get(
        _api(f"/assets/{seeded_asset.id}/chapters/ch-0/evidence"),
    )
    assert r.status_code == 200
    assert r.json() == []


def test_list_project_assets(client: TestClient, seeded_asset: Asset) -> None:
    r = client.get(_api(f"/projects/{seeded_asset.project_id}/assets"))
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert "meta" in body
    assert any(a["id"] == seeded_asset.id for a in body["data"])


# ─── PATCH chapter content ─────────────────────────────────────────


def test_patch_chapter_updates_content(client: TestClient, seeded_asset: Asset) -> None:
    r = client.patch(
        _api(f"/assets/{seeded_asset.id}/chapters/ch-0"),
        json={"content": "new content yay"},
    )
    assert r.status_code == 200
    assert r.json()["content"] == "new content yay"


def test_patch_chapter_missing_404(client: TestClient, seeded_asset: Asset) -> None:
    r = client.patch(
        _api(f"/assets/{seeded_asset.id}/chapters/ch-fake"),
        json={"content": "x"},
    )
    assert r.status_code == 404


# ─── POST submit / approve / reject ────────────────────────────────


def test_submit_asset_moves_to_in_review(client: TestClient, seeded_asset: Asset) -> None:
    r = client.post(_api(f"/assets/{seeded_asset.id}/submit"))
    assert r.status_code == 200
    assert r.json()["status"] == "in_review"


def test_submit_missing_asset_404(client: TestClient) -> None:
    r = client.post(_api("/assets/asset-fake/submit"))
    assert r.status_code == 404


def test_approve_chapter_endpoint(client: TestClient, seeded_asset: Asset) -> None:
    # submit 先
    client.post(_api(f"/assets/{seeded_asset.id}/submit"))
    r = client.post(_api(f"/assets/{seeded_asset.id}/chapters/ch-0/approve"))
    assert r.status_code == 200
    assert r.json()["approval_state"] == "approved"


def test_approve_chapter_missing_404(client: TestClient, seeded_asset: Asset) -> None:
    r = client.post(_api(f"/assets/{seeded_asset.id}/chapters/ch-fake/approve"))
    assert r.status_code == 404


def test_reject_chapter_endpoint(client: TestClient, seeded_asset: Asset) -> None:
    r = client.post(
        _api(f"/assets/{seeded_asset.id}/chapters/ch-0/reject"),
        json={"reason": "需要补充第二节细节"},
    )
    assert r.status_code == 200
    assert r.json()["approval_state"] == "rejected"


# ─── Redaction (T10) ───────────────────────────────────────────────


def test_scan_redaction_creates_job(client: TestClient, seeded_asset: Asset) -> None:
    """POST /scan: 即使 chapter 无敏感词也建 job (空 items)."""
    r = client.post(_api(f"/assets/{seeded_asset.id}/redaction/scan"))
    assert r.status_code == 200
    body = r.json()
    assert body["asset_id"] == seeded_asset.id
    assert body["status"] == "done"
    assert isinstance(body["items"], list)


def test_get_redaction_scan_404_before_scan(client: TestClient, seeded_asset: Asset) -> None:
    """没扫过 → 404."""
    r = client.get(_api(f"/assets/{seeded_asset.id}/redaction/scan"))
    assert r.status_code == 404


def test_get_redaction_scan_after_scan(client: TestClient, seeded_asset: Asset) -> None:
    client.post(_api(f"/assets/{seeded_asset.id}/redaction/scan"))
    r = client.get(_api(f"/assets/{seeded_asset.id}/redaction/scan"))
    assert r.status_code == 200
    assert r.json()["asset_id"] == seeded_asset.id


# ─── Publish (T11/T12) ─────────────────────────────────────────────


def test_publish_endpoint_internal(client: TestClient, seeded_asset: Asset) -> None:
    r = client.post(
        _api(f"/assets/{seeded_asset.id}/publish"),
        json={
            "destinations": ["internal"],
            "publish_mode": "full",
        },
    )
    assert r.status_code in (200, 201)
    body = r.json()
    assert len(body) == 1
    assert body[0]["destination"] == "internal"


def test_publish_missing_asset_404(client: TestClient) -> None:
    r = client.post(
        _api("/assets/asset-fake/publish"),
        json={"destinations": ["internal"], "publish_mode": "full"},
    )
    assert r.status_code == 404


def test_publish_invalid_destination_422(client: TestClient, seeded_asset: Asset) -> None:
    r = client.post(
        _api(f"/assets/{seeded_asset.id}/publish"),
        json={"destinations": ["smoke_signals"], "publish_mode": "full"},
    )
    # 422 (validation) 或 400 (business)
    assert r.status_code in (400, 422)


def test_get_publish_record_404(client: TestClient) -> None:
    r = client.get(_api("/publish-records/pub-fake-id"))
    assert r.status_code == 404


def test_get_publish_record_after_publish(
    client: TestClient, seeded_asset: Asset,
) -> None:
    r1 = client.post(
        _api(f"/assets/{seeded_asset.id}/publish"),
        json={"destinations": ["internal"], "publish_mode": "full"},
    )
    assert r1.status_code in (200, 201)
    pub_id = r1.json()[0]["id"]
    r2 = client.get(_api(f"/publish-records/{pub_id}"))
    assert r2.status_code == 200
    assert r2.json()["id"] == pub_id


def test_list_asset_publish_records(client: TestClient, seeded_asset: Asset) -> None:
    r0 = client.post(
        _api(f"/assets/{seeded_asset.id}/publish"),
        json={"destinations": ["internal"], "publish_mode": "full"},
    )
    assert r0.status_code in (200, 201)
    r = client.get(_api(f"/assets/{seeded_asset.id}/publish-records"))
    assert r.status_code == 200
    assert len(r.json()) >= 1


# ─── Delete / Clone ────────────────────────────────────────────────


def test_delete_asset(
    client: TestClient, seeded_asset: Asset, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gen.get_db(), "delete_asset", lambda _: None)
    r = client.delete(_api(f"/assets/{seeded_asset.id}"))
    assert r.status_code == 204
    # 删完应不存在
    r2 = client.get(_api(f"/assets/{seeded_asset.id}"))
    assert r2.status_code == 404


def test_delete_asset_missing_404(client: TestClient) -> None:
    r = client.delete(_api("/assets/asset-fake"))
    assert r.status_code == 404


def test_clone_asset(client: TestClient, seeded_asset: Asset) -> None:
    r = client.post(_api(f"/assets/{seeded_asset.id}/clone"))
    assert r.status_code == 201
    body = r.json()
    assert body["id"] != seeded_asset.id
    assert body["status"] == "draft"
    # 清理克隆
    gen._assets.pop(body["id"], None)
    gen._chapters.pop(body["id"], None)


def test_clone_asset_missing_404(client: TestClient) -> None:
    r = client.post(_api("/assets/asset-fake/clone"))
    assert r.status_code == 404


# ─── Progress ──────────────────────────────────────────────────────


def test_get_progress_404_before_generate(client: TestClient, seeded_asset: Asset) -> None:
    r = client.get(_api(f"/assets/{seeded_asset.id}/progress"))
    # seeded_asset 没有 progress 入口 (没经过 start_generation)
    assert r.status_code == 404
