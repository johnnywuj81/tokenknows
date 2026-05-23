"""T89 · list endpoint enrich knowledge_graph asset 的 kg_summary."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.http_api.generation import router as gen_router
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.asset import Asset, Chapter
from app.services import generation_service


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    generation_service._assets.clear()
    generation_service._chapters.clear()
    generation_service._progress.clear()
    generation_service._sse_queues.clear()
    yield


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(gen_router)
    return TestClient(app)


def _seed_kg(
    *,
    asset_id: str = "a-kg",
    project_id: str = "p-1",
    nodes: list[dict] | None = None,
    edges: list[dict] | None = None,
) -> Asset:
    now = datetime.now(timezone.utc)
    asset = Asset(
        id=asset_id, project_id=project_id, type="knowledge_graph",
        title="测试图谱", status="draft", current_version=1,
        template_id=None, created_by="u",
        created_at=now, updated_at=now,
    )
    generation_service._assets[asset_id] = asset
    layout = {
        "schema_version": "kg.v1",
        "nodes": nodes or [],
        "edges": edges or [],
        "layout_hints": {"algorithm": "dagre", "rankdir": "LR"},
    }
    chapter = Chapter(
        id=f"ch-{asset_id}",
        asset_id=asset_id,
        order_index=0,
        title="实体关系图谱",
        content="# 图谱",
        layout=layout,
    )
    generation_service._chapters[asset_id] = [chapter]
    return asset


def _seed_non_kg(asset_id: str, atype: str) -> Asset:
    now = datetime.now(timezone.utc)
    asset = Asset(
        id=asset_id, project_id="p-1", type=atype,  # type: ignore[arg-type]
        title=f"{atype} 文档", status="draft", current_version=1,
        template_id=None, created_by="u",
        created_at=now, updated_at=now,
    )
    generation_service._assets[asset_id] = asset
    return asset


def test_list_endpoint_enriches_kg_with_summary(client):
    _seed_kg(
        asset_id="a-kg-1",
        nodes=[{"id": "n1"}, {"id": "n2"}, {"id": "n3"}],
        edges=[{"id": "e1"}, {"id": "e2"}],
    )
    r = client.get("/projects/p-1/assets")
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 1
    kg = body["data"][0]
    assert kg["kg_summary"] is not None
    assert kg["kg_summary"]["node_count"] == 3
    assert kg["kg_summary"]["edge_count"] == 2


def test_list_endpoint_non_kg_assets_get_null_summary(client):
    _seed_non_kg("a-weekly", "weekly_report")
    _seed_non_kg("a-adr", "adr")
    r = client.get("/projects/p-1/assets")
    body = r.json()
    for item in body["data"]:
        assert item["kg_summary"] is None


def test_list_endpoint_kg_no_chapter_kg_summary_null(client):
    """asset.type=knowledge_graph 但 chapter 缺失 (尚未生成完) → kg_summary=None."""
    now = datetime.now(timezone.utc)
    asset = Asset(
        id="a-kg-no-ch", project_id="p-1", type="knowledge_graph",
        title="生成中", status="generating", current_version=1,
        template_id=None, created_by="u",
        created_at=now, updated_at=now,
    )
    generation_service._assets["a-kg-no-ch"] = asset
    # 不 seed chapter
    r = client.get("/projects/p-1/assets")
    body = r.json()
    assert body["data"][0]["kg_summary"] is None


def test_list_endpoint_mixed_types_only_kg_enriched(client):
    _seed_kg(asset_id="a-kg-1", nodes=[{"id": "n"}], edges=[])
    _seed_non_kg("a-wr", "weekly_report")
    _seed_kg(asset_id="a-kg-2", nodes=[{"id": "x"}, {"id": "y"}], edges=[{"id": "e"}])
    r = client.get("/projects/p-1/assets")
    body = r.json()
    assert len(body["data"]) == 3
    kg_items = [a for a in body["data"] if a["type"] == "knowledge_graph"]
    non_kg = [a for a in body["data"] if a["type"] != "knowledge_graph"]
    assert all(a["kg_summary"] is not None for a in kg_items)
    assert all(a["kg_summary"] is None for a in non_kg)


def test_list_endpoint_filter_type_knowledge_graph(client):
    _seed_kg(asset_id="a-kg-1", nodes=[{"id": "n"}], edges=[])
    _seed_non_kg("a-wr", "weekly_report")
    r = client.get("/projects/p-1/assets?type=knowledge_graph")
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["type"] == "knowledge_graph"
    assert body["data"][0]["kg_summary"]["node_count"] == 1


# v1.3.1 T95 · thumbnail_svg enrich
def test_list_endpoint_includes_thumbnail_svg_when_present(client):
    """assess stage 写到 layout.thumbnail_svg → list endpoint enrich 到 kg_summary."""
    _seed_kg(
        asset_id="a-thumb",
        nodes=[{"id": "n1"}],
        edges=[],
    )
    chapter = generation_service._chapters["a-thumb"][0]
    layout_dict = dict(chapter.layout or {})
    layout_dict["thumbnail_svg"] = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 180"></svg>'
    )
    chapter.layout = layout_dict
    r = client.get("/projects/p-1/assets")
    body = r.json()
    assert "thumbnail_svg" in body["data"][0]["kg_summary"]
    assert body["data"][0]["kg_summary"]["thumbnail_svg"].startswith("<svg")


def test_list_endpoint_no_thumbnail_when_absent(client):
    """layout 没有 thumbnail_svg → kg_summary 不含该 key."""
    _seed_kg(asset_id="a-no-thumb", nodes=[{"id": "n"}], edges=[])
    r = client.get("/projects/p-1/assets")
    summary = r.json()["data"][0]["kg_summary"]
    assert "thumbnail_svg" not in summary
    assert "thumbnail_png_b64" not in summary


# v1.5 T100 · PNG b64 enrich
def test_list_endpoint_includes_thumbnail_png_when_present(client):
    _seed_kg(asset_id="a-png", nodes=[{"id": "n1"}], edges=[])
    chapter = generation_service._chapters["a-png"][0]
    layout_dict = dict(chapter.layout or {})
    layout_dict["thumbnail_png_b64"] = "iVBORw0KGgo="  # 占位 base64
    chapter.layout = layout_dict
    r = client.get("/projects/p-1/assets")
    summary = r.json()["data"][0]["kg_summary"]
    assert summary["thumbnail_png_b64"] == "iVBORw0KGgo="
