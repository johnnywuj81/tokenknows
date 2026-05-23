"""v1.5 T99 · global_registry (跨 project) 单测 + API 集成测.

验:
  - publish_to_global: 单 entity → 新 global; 第二 project 同名 → link 同一 global
  - 1 project 已 link 后重复 publish → no-op (同 global)
  - canonical match 跨 project (同 type+canonical 自动 link)
  - cross-type 不合并 (即使 canonical 同)
  - unlink: 移除最后 link → global 自动删除
  - list_globals filter type/q/min_projects
  - API: publish / unlink / get_for_project / list / get / list_linked
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
from app.services.knowledge_graph import entity_registry as p_reg
from app.services.knowledge_graph import global_registry as g_reg


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    generation_service._assets.clear()
    generation_service._chapters.clear()
    p_reg.clear_for_test()
    g_reg.clear_for_test()
    from app.services.knowledge_graph import audit as audit_module
    audit_module.clear_for_test()
    yield


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(ent_router)
    return TestClient(app)


def _make_pent(project_id: str, label: str = "Alice", ntype: str = "person") -> str:
    return p_reg.register_entity(
        project_id=project_id, node_id=f"n_{label}_{project_id}",
        node_type=ntype, label=label,
        asset_id=f"a_{project_id}", chapter_id=f"ch_{project_id}",
    )


# ── pure ──────────────────────────────────────────────────────────


def test_publish_creates_new_global():
    pid = _make_pent("p-1", "Alice")
    gent = g_reg.publish_to_global(pid, actor_id="u-1")
    assert gent is not None
    assert gent.id.startswith("gent_")
    assert gent.label == "Alice"
    assert gent.project_count == 1
    assert gent.created_by == "u-1"


def test_publish_cross_project_links_same_global():
    a = _make_pent("p-1", "Alice")
    b = _make_pent("p-2", "Alice")
    ga = g_reg.publish_to_global(a)
    gb = g_reg.publish_to_global(b)
    assert ga.id == gb.id
    assert gb.project_count == 2


def test_publish_same_canonical_lowercase_links():
    a = _make_pent("p-1", "Alice")
    b = _make_pent("p-2", "  ALICE ")  # canonical 同
    ga = g_reg.publish_to_global(a)
    gb = g_reg.publish_to_global(b)
    assert ga.id == gb.id
    # 'ALICE' 进 aliases
    assert "  ALICE " in gb.aliases or "ALICE" in gb.aliases


def test_publish_idempotent_for_same_project_entity():
    pid = _make_pent("p-1", "Alice")
    g1 = g_reg.publish_to_global(pid)
    g2 = g_reg.publish_to_global(pid)
    assert g1.id == g2.id
    assert g1.project_count == 1  # 不重复 link 自身


def test_publish_cross_type_does_not_merge():
    a = p_reg.register_entity(
        project_id="p-1", node_id="n", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    b = p_reg.register_entity(
        project_id="p-2", node_id="n", node_type="concept",
        label="Alice", asset_id="a-2", chapter_id="ch-2",
    )
    ga = g_reg.publish_to_global(a)
    gb = g_reg.publish_to_global(b)
    assert ga.id != gb.id


def test_publish_unknown_project_entity():
    assert g_reg.publish_to_global("not-real") is None


def test_unlink_removes_link():
    a = _make_pent("p-1", "Alice")
    b = _make_pent("p-2", "Alice")
    g_reg.publish_to_global(a)
    g_reg.publish_to_global(b)
    ok = g_reg.unlink_project_entity(a)
    assert ok is True
    # a 解链, global 还在 (b 还在 link)
    g_after = g_reg.get_global_for_project_entity(b)
    assert g_after is not None
    assert g_after.project_count == 1


def test_unlink_last_link_deletes_global():
    a = _make_pent("p-1", "Alice")
    gent = g_reg.publish_to_global(a)
    g_reg.unlink_project_entity(a)
    assert g_reg.get_global(gent.id) is None


def test_unlink_non_linked_returns_false():
    pid = _make_pent("p-1", "X")
    assert g_reg.unlink_project_entity(pid) is False


def test_list_globals_filter_min_projects():
    a1 = _make_pent("p-1", "Alice")
    a2 = _make_pent("p-2", "Alice")
    b1 = _make_pent("p-1", "Bob")
    g_reg.publish_to_global(a1)
    g_reg.publish_to_global(a2)
    g_reg.publish_to_global(b1)
    # min_projects=2 → 只 Alice
    res = g_reg.list_globals(min_projects=2)
    assert len(res) == 1
    assert res[0].label == "Alice"


def test_list_globals_filter_query():
    a = _make_pent("p-1", "Alice")
    b = _make_pent("p-1", "Bob")
    g_reg.publish_to_global(a)
    g_reg.publish_to_global(b)
    res = g_reg.list_globals(query="alice")
    assert len(res) == 1


def test_get_linked_project_entities():
    a = _make_pent("p-1", "Alice")
    b = _make_pent("p-2", "Alice")
    gent = g_reg.publish_to_global(a)
    g_reg.publish_to_global(b)
    linked = g_reg.get_linked_project_entities(gent.id)
    project_ids = {e.project_id for e in linked}
    assert project_ids == {"p-1", "p-2"}


# ── API ──────────────────────────────────────────────────────────


def test_api_publish_global(client):
    pid = _make_pent("p-1", "Alice")
    r = client.post(f"/entities/{pid}/publish_global")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"] == "Alice"
    assert body["project_count"] == 1


def test_api_publish_unknown_404(client):
    r = client.post("/entities/no-such/publish_global")
    assert r.status_code == 404


def test_api_unlink_global(client):
    pid = _make_pent("p-1", "Alice")
    client.post(f"/entities/{pid}/publish_global")
    r = client.delete(f"/entities/{pid}/global")
    assert r.status_code == 204


def test_api_unlink_unknown_project_entity_404(client):
    r = client.delete("/entities/no-such/global")
    assert r.status_code == 404


def test_api_unlink_not_published_404(client):
    pid = _make_pent("p-1", "Alice")  # 不 publish
    r = client.delete(f"/entities/{pid}/global")
    assert r.status_code == 404


def test_api_get_global_for_project_entity(client):
    pid = _make_pent("p-1", "Alice")
    client.post(f"/entities/{pid}/publish_global")
    r = client.get(f"/entities/{pid}/global")
    assert r.status_code == 200
    assert r.json()["label"] == "Alice"


def test_api_get_global_for_unpublished_404(client):
    pid = _make_pent("p-1", "Alice")
    r = client.get(f"/entities/{pid}/global")
    assert r.status_code == 404


def test_api_list_global_entities(client):
    a = _make_pent("p-1", "Alice")
    b = _make_pent("p-2", "Alice")
    client.post(f"/entities/{a}/publish_global")
    client.post(f"/entities/{b}/publish_global")
    r = client.get("/global/entities?min_projects=2")
    body = r.json()
    assert len(body) == 1
    assert body[0]["project_count"] == 2


def test_api_get_global_entity_and_linked(client):
    a = _make_pent("p-1", "Alice")
    b = _make_pent("p-2", "Alice")
    g1 = client.post(f"/entities/{a}/publish_global").json()
    client.post(f"/entities/{b}/publish_global")
    r = client.get(f"/global/entities/{g1['id']}")
    assert r.status_code == 200
    r2 = client.get(f"/global/entities/{g1['id']}/projects")
    pids = {e["project_id"] for e in r2.json()}
    assert pids == {"p-1", "p-2"}
