"""v1.3.1 T96 · entity_registry 单测 + API 集成测.

验:
  - register_entity 同 project 同 type 同 canonical_label → 合并 entity
  - 跨 asset 合并: 同 entity 出现在 N 个 asset, source_refs 累加, asset_count = N
  - 不同 type 同 label 不合并 (person 'Alice' ≠ concept 'Alice')
  - 不同 project 不合并
  - canonical: trim + lowercase + collapse whitespace
  - aliases: label 变体收集 (label 不同时累入 aliases)
  - list_entities filter type / q / min_assets
  - get_sources 聚合 asset 维度
  - get_entity_for_node 反查
  - API: GET /projects/:pid/entities, /entities/:eid, /entities/:eid/sources
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.http_api.entities import router as ent_router
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.asset import Asset
from app.services import generation_service
from app.services.knowledge_graph import entity_registry as registry


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    generation_service._assets.clear()
    generation_service._chapters.clear()
    registry.clear_for_test()
    yield


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(ent_router)
    return TestClient(app)


def _seed_asset(asset_id: str, project_id: str = "p-1", title: str = "doc") -> Asset:
    now = datetime.now(timezone.utc)
    asset = Asset(
        id=asset_id, project_id=project_id, type="knowledge_graph",
        title=title, status="draft", current_version=1, template_id=None,
        created_by="u", created_at=now, updated_at=now,
    )
    generation_service._assets[asset_id] = asset
    return asset


# ── pure-function tests ───────────────────────────────────────────


def test_register_creates_new_entity():
    eid = registry.register_entity(
        project_id="p-1", node_id="n_alice", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    assert eid.startswith("ent_")
    ent = registry.get_entity(eid)
    assert ent is not None
    assert ent.label == "Alice"
    assert ent.canonical_label == "alice"
    assert ent.asset_count == 1


def test_same_label_same_type_same_project_merges():
    e1 = registry.register_entity(
        project_id="p-1", node_id="n_a", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    e2 = registry.register_entity(
        project_id="p-1", node_id="n_b", node_type="person",
        label="alice", asset_id="a-2", chapter_id="ch-2",
    )
    assert e1 == e2  # 合并
    ent = registry.get_entity(e1)
    assert ent.asset_count == 2
    assert len(ent.source_refs) == 2


def test_canonical_trim_and_lowercase_and_collapse_whitespace():
    e1 = registry.register_entity(
        project_id="p-1", node_id="n1", node_type="person",
        label="Alice  Wong",  # 双空格
        asset_id="a-1", chapter_id="ch-1",
    )
    e2 = registry.register_entity(
        project_id="p-1", node_id="n2", node_type="person",
        label=" alice wong ",
        asset_id="a-2", chapter_id="ch-2",
    )
    assert e1 == e2
    assert registry.get_entity(e1).canonical_label == "alice wong"


def test_different_type_does_not_merge():
    e1 = registry.register_entity(
        project_id="p-1", node_id="n1", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    e2 = registry.register_entity(
        project_id="p-1", node_id="n2", node_type="concept",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    assert e1 != e2


def test_different_project_does_not_merge():
    e1 = registry.register_entity(
        project_id="p-1", node_id="n1", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    e2 = registry.register_entity(
        project_id="p-2", node_id="n1", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    assert e1 != e2


def test_aliases_accumulate():
    e1 = registry.register_entity(
        project_id="p-1", node_id="n1", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    registry.register_entity(
        project_id="p-1", node_id="n2", node_type="person",
        label="Alice Wong",  # 不同 label 但同 canonical? 不,canonical 不同
        asset_id="a-2", chapter_id="ch-2",
    )
    # 'Alice Wong' canonical='alice wong' ≠ 'alice' → 不合并
    ent = registry.get_entity(e1)
    assert ent.label == "Alice"
    # 现在再注册一个 canonical=alice 但 label 不同
    registry.register_entity(
        project_id="p-1", node_id="n3", node_type="person",
        label="ALICE", asset_id="a-3", chapter_id="ch-3",
    )
    ent = registry.get_entity(e1)
    assert "ALICE" in ent.aliases
    assert ent.label == "Alice"  # 首次见的不变


def test_same_node_ref_no_duplicate():
    """同 (asset_id, chapter_id, node_id) 多次 register 不累加."""
    eid = registry.register_entity(
        project_id="p-1", node_id="n1", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    registry.register_entity(
        project_id="p-1", node_id="n1", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    ent = registry.get_entity(eid)
    assert len(ent.source_refs) == 1


def test_register_asset_nodes_batch():
    out = registry.register_asset_nodes(
        project_id="p-1", asset_id="a-1", chapter_id="ch-1",
        nodes=[
            {"id": "n1", "type": "person", "label": "Alice"},
            {"id": "n2", "type": "event", "label": "Outage"},
            {"id": "n3", "type": "concept", "label": "SLA"},
        ],
    )
    assert len(out) == 3
    assert all(v.startswith("ent_") for v in out.values())


def test_register_asset_nodes_skips_invalid_type_or_id():
    out = registry.register_asset_nodes(
        project_id="p-1", asset_id="a-1", chapter_id="ch-1",
        nodes=[
            {"id": "n1", "type": "person", "label": "A"},
            {"id": "", "type": "person", "label": "B"},  # 空 id
            {"id": "n3", "type": "cluster", "label": "C"},  # 非法 type
            {"id": "n4", "type": "person"},  # 缺 label → "" 仍接受
        ],
    )
    assert "n1" in out
    assert "n4" in out
    assert "" not in out
    assert "n3" not in out


def test_get_entity_for_node_lookup():
    eid = registry.register_entity(
        project_id="p-1", node_id="n_alice", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    ent = registry.get_entity_for_node("a-1", "n_alice")
    assert ent is not None
    assert ent.id == eid


def test_list_entities_filter_type_and_query():
    registry.register_entity(
        project_id="p-1", node_id="n1", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    registry.register_entity(
        project_id="p-1", node_id="n2", node_type="event",
        label="Outage", asset_id="a-1", chapter_id="ch-1",
    )
    # by type
    persons = registry.list_entities("p-1", entity_type="person")
    assert len(persons) == 1
    assert persons[0].label == "Alice"
    # by query
    matched = registry.list_entities("p-1", query="alice")
    assert len(matched) == 1
    no_match = registry.list_entities("p-1", query="bob")
    assert no_match == []


def test_list_entities_min_assets_filters():
    """min_assets=2 时, 只出现在 1 个 asset 的实体被过滤."""
    registry.register_entity(
        project_id="p-1", node_id="n1", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    registry.register_entity(
        project_id="p-1", node_id="n2", node_type="person",
        label="Alice", asset_id="a-2", chapter_id="ch-2",
    )
    registry.register_entity(
        project_id="p-1", node_id="n3", node_type="person",
        label="Bob", asset_id="a-1", chapter_id="ch-1",
    )
    # Alice 在 2 个 asset, Bob 在 1 个
    res = registry.list_entities("p-1", min_asset_count=2)
    assert len(res) == 1
    assert res[0].label == "Alice"


def test_list_entities_sorted_by_asset_count_desc():
    # Alice 在 3 个 asset
    for i in range(3):
        registry.register_entity(
            project_id="p-1", node_id=f"n{i}", node_type="person",
            label="Alice", asset_id=f"a-{i}", chapter_id="ch",
        )
    # Bob 在 1 个 asset
    registry.register_entity(
        project_id="p-1", node_id="nb", node_type="person",
        label="Bob", asset_id="a-x", chapter_id="ch",
    )
    res = registry.list_entities("p-1")
    assert res[0].label == "Alice"
    assert res[1].label == "Bob"


def test_get_sources_aggregates_by_asset():
    eid = registry.register_entity(
        project_id="p-1", node_id="n1", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    registry.register_entity(
        project_id="p-1", node_id="n2", node_type="person",
        label="Alice", asset_id="a-2", chapter_id="ch-2",
    )
    registry.register_entity(
        project_id="p-1", node_id="n3", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",  # 同 asset 不同 node
    )

    def lookup(aid: str):
        if aid == "a-1":
            return {"title": "Doc1", "type": "knowledge_graph"}
        if aid == "a-2":
            return {"title": "Doc2", "type": "knowledge_graph"}
        return None

    sources = registry.get_sources(eid, asset_lookup=lookup)
    assert len(sources) == 2  # a-1 + a-2
    a1 = next(s for s in sources if s.asset_id == "a-1")
    assert set(a1.node_ids) == {"n1", "n3"}


def test_get_sources_skips_deleted_asset():
    eid = registry.register_entity(
        project_id="p-1", node_id="n1", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    sources = registry.get_sources(eid, asset_lookup=lambda aid: None)
    assert sources == []


# ── API integration tests ─────────────────────────────────────────


def test_api_list_entities(client):
    _seed_asset("a-1")
    _seed_asset("a-2", title="另一文档")
    registry.register_entity(
        project_id="p-1", node_id="n1", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    registry.register_entity(
        project_id="p-1", node_id="n2", node_type="person",
        label="Alice", asset_id="a-2", chapter_id="ch-2",
    )
    r = client.get("/projects/p-1/entities")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["label"] == "Alice"


def test_api_list_entities_min_assets_filter(client):
    _seed_asset("a-1")
    _seed_asset("a-2")
    registry.register_entity(
        project_id="p-1", node_id="n1", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    registry.register_entity(
        project_id="p-1", node_id="n2", node_type="person",
        label="Bob", asset_id="a-1", chapter_id="ch-1",
    )
    registry.register_entity(
        project_id="p-1", node_id="n3", node_type="person",
        label="Alice", asset_id="a-2", chapter_id="ch-2",
    )
    # min_assets=2: Alice (2 asset) 才返回
    r = client.get("/projects/p-1/entities?min_assets=2")
    body = r.json()
    assert len(body) == 1
    assert body[0]["label"] == "Alice"


def test_api_get_entity_404(client):
    r = client.get("/entities/no-such")
    assert r.status_code == 404


def test_api_get_entity_sources(client):
    _seed_asset("a-1", title="Doc1")
    _seed_asset("a-2", title="Doc2")
    eid = registry.register_entity(
        project_id="p-1", node_id="n1", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    registry.register_entity(
        project_id="p-1", node_id="n2", node_type="person",
        label="Alice", asset_id="a-2", chapter_id="ch-2",
    )
    r = client.get(f"/entities/{eid}/sources")
    assert r.status_code == 200
    body = r.json()
    titles = {s["asset_title"] for s in body}
    assert titles == {"Doc1", "Doc2"}


def test_api_get_node_entity(client):
    _seed_asset("a-1")
    eid = registry.register_entity(
        project_id="p-1", node_id="n_alice", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    r = client.get("/assets/a-1/nodes/n_alice/entity")
    assert r.status_code == 200
    assert r.json()["id"] == eid


def test_api_get_node_entity_404_for_unknown(client):
    r = client.get("/assets/a-X/nodes/n-X/entity")
    assert r.status_code == 404
