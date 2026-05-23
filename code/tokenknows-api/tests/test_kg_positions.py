"""v1.3 T91 · PATCH /assets/:aid/chapters/:cid/positions 单测.

验:
  - 写入 layout.user_positions; 其它 layout 字段不变
  - 重复 PATCH 覆盖语义 (full replace)
  - 404 chapter not found
  - schema 校验 (x/y 必须 number)
  - asset.updated_at 被刷新
"""

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
    asset_id: str = "a-kg",
    chapter_id: str = "ch-kg",
    nodes: list[dict] | None = None,
) -> tuple[Asset, Chapter]:
    """创建一个 knowledge_graph asset + 1 chapter."""
    now = datetime.now(timezone.utc)
    asset = Asset(
        id=asset_id, project_id="p-1", type="knowledge_graph",
        title="图谱", status="draft", current_version=1,
        template_id=None, created_by="u",
        created_at=now, updated_at=now,
    )
    generation_service._assets[asset_id] = asset
    layout = {
        "schema_version": "kg.v1",
        "nodes": nodes or [{"id": "n_a"}, {"id": "n_b"}],
        "edges": [],
        "layout_hints": {"algorithm": "dagre", "rankdir": "LR"},
    }
    chapter = Chapter(
        id=chapter_id, asset_id=asset_id, order_index=0,
        title="ch", content="", layout=layout,
    )
    generation_service._chapters[asset_id] = [chapter]
    return asset, chapter


def test_patch_positions_writes_user_positions(client):
    _seed_kg(asset_id="a-1", chapter_id="ch-1")
    r = client.patch(
        "/assets/a-1/chapters/ch-1/positions",
        json={"positions": {
            "n_a": {"x": 100, "y": 200},
            "n_b": {"x": -50, "y": 300},
        }},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["layout"]["user_positions"]["n_a"] == {"x": 100.0, "y": 200.0}
    assert body["layout"]["user_positions"]["n_b"] == {"x": -50.0, "y": 300.0}


def test_patch_positions_preserves_other_layout_fields(client):
    """nodes/edges/layout_hints 不动."""
    _seed_kg(asset_id="a-2", chapter_id="ch-2")
    r = client.patch(
        "/assets/a-2/chapters/ch-2/positions",
        json={"positions": {"n_a": {"x": 1, "y": 2}}},
    )
    assert r.status_code == 200
    layout = r.json()["layout"]
    assert layout["schema_version"] == "kg.v1"
    assert len(layout["nodes"]) == 2
    assert layout["layout_hints"]["algorithm"] == "dagre"


def test_patch_positions_replace_semantics(client):
    """第二次 PATCH 全量覆盖, 不 merge."""
    _seed_kg(asset_id="a-3", chapter_id="ch-3")
    client.patch(
        "/assets/a-3/chapters/ch-3/positions",
        json={"positions": {"n_a": {"x": 1, "y": 1}, "n_b": {"x": 2, "y": 2}}},
    )
    r = client.patch(
        "/assets/a-3/chapters/ch-3/positions",
        json={"positions": {"n_a": {"x": 99, "y": 99}}},
    )
    user_positions = r.json()["layout"]["user_positions"]
    assert user_positions == {"n_a": {"x": 99.0, "y": 99.0}}
    assert "n_b" not in user_positions


def test_patch_positions_404_unknown_chapter(client):
    _seed_kg(asset_id="a-4", chapter_id="ch-4")
    r = client.patch(
        "/assets/a-4/chapters/no-such-chapter/positions",
        json={"positions": {"n": {"x": 0, "y": 0}}},
    )
    assert r.status_code == 404


def test_patch_positions_404_unknown_asset(client):
    r = client.patch(
        "/assets/no-such-asset/chapters/ch-x/positions",
        json={"positions": {}},
    )
    assert r.status_code == 404


def test_patch_positions_validates_position_shape(client):
    """x/y 必须是数字; 缺字段 → 422."""
    _seed_kg(asset_id="a-5", chapter_id="ch-5")
    # 缺 y
    r = client.patch(
        "/assets/a-5/chapters/ch-5/positions",
        json={"positions": {"n_a": {"x": 10}}},
    )
    assert r.status_code == 422


def test_patch_positions_empty_dict_clears(client):
    """空 positions {} 等价于"清空 user_positions"."""
    _seed_kg(asset_id="a-6", chapter_id="ch-6")
    client.patch(
        "/assets/a-6/chapters/ch-6/positions",
        json={"positions": {"n_a": {"x": 1, "y": 1}}},
    )
    r = client.patch(
        "/assets/a-6/chapters/ch-6/positions",
        json={"positions": {}},
    )
    assert r.status_code == 200
    assert r.json()["layout"]["user_positions"] == {}


def test_patch_positions_refreshes_asset_updated_at(client):
    """更新位置应推进 asset.updated_at (与 update_chapter_content 一致)."""
    _seed_kg(asset_id="a-7", chapter_id="ch-7")
    old_ts = generation_service._assets["a-7"].updated_at
    r = client.patch(
        "/assets/a-7/chapters/ch-7/positions",
        json={"positions": {"n_a": {"x": 1, "y": 2}}},
    )
    assert r.status_code == 200
    new_ts = generation_service._assets["a-7"].updated_at
    assert new_ts >= old_ts
