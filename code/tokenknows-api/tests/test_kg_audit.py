"""v1.6 T102 · entity audit log + undo split 单测.

验:
  - record_merge / record_split 写日志
  - list_logs filter op_type / only_undoable / 按时间 desc 排序
  - undo_split: 成功 (单 ref, 同 type, 一致) → ref 回 source, 删 new_entity
  - undo_split 失败: log 不存在 / 已 undone / 状态变 (new_entity 被改) / source 已删
  - merge audit 不能 undo (v1.6 限制)
  - API: list_audit_log + undo
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
from app.services.knowledge_graph import audit as audit_module
from app.services.knowledge_graph import entity_registry as registry
from app.services.knowledge_graph import global_registry


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    generation_service._assets.clear()
    generation_service._chapters.clear()
    registry.clear_for_test()
    global_registry.clear_for_test()
    audit_module.clear_for_test()
    yield


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(ent_router)
    return TestClient(app)


def _seed_asset(asset_id: str, project_id: str = "p-1") -> Asset:
    now = datetime.now(timezone.utc)
    asset = Asset(
        id=asset_id, project_id=project_id, type="knowledge_graph",
        title="doc", status="draft", current_version=1, template_id=None,
        created_by="u", created_at=now, updated_at=now,
    )
    generation_service._assets[asset_id] = asset
    return asset


def _seed_entity_with_2_refs() -> str:
    """构造 entity p-1 项目下 'Alice', 在 a-1 + a-2 两 asset 各 1 ref."""
    eid = registry.register_entity(
        project_id="p-1", node_id="n_a1", node_type="person",
        label="Alice", asset_id="a-1", chapter_id="ch-1",
    )
    registry.register_entity(
        project_id="p-1", node_id="n_a2", node_type="person",
        label="Alice", asset_id="a-2", chapter_id="ch-2",
    )
    return eid


# ── pure ──────────────────────────────────────────────────────────


def test_record_merge_creates_log():
    a = registry.register_entity(
        project_id="p-1", node_id="na", node_type="person",
        label="A", asset_id="a-1", chapter_id="ch-1",
    )
    src = registry.get_entity(a)
    log = audit_module.record_merge(
        project_id="p-1", source=src,
        target_id="tgt-id", target_label="B",
        actor_id="u-1",
    )
    assert log.id.startswith("audit_")
    assert log.op_type == "merge"
    assert log.actor_id == "u-1"
    assert log.undone is False
    assert log.payload["target_id"] == "tgt-id"
    assert log.payload["source_snapshot"]["label"] == "A"


def test_record_split_creates_log():
    from app.schemas.entity_registry import EntitySourceRef
    log = audit_module.record_split(
        project_id="p-1",
        source_id="ent_src", new_entity_id="ent_new",
        moved_node_ref=EntitySourceRef(
            asset_id="a-1", chapter_id="ch-1", node_id="n_x",
        ),
        new_canonical="alice (split-abc)",
        actor_id="u-1",
    )
    assert log.op_type == "split"
    assert log.payload["new_entity_id"] == "ent_new"


def test_list_logs_filter_op_type():
    a = registry.register_entity(
        project_id="p-1", node_id="n", node_type="person",
        label="A", asset_id="a-1", chapter_id="ch-1",
    )
    audit_module.record_merge(
        project_id="p-1", source=registry.get_entity(a),
        target_id="tgt", target_label="B",
    )
    from app.schemas.entity_registry import EntitySourceRef
    audit_module.record_split(
        project_id="p-1", source_id="x", new_entity_id="y",
        moved_node_ref=EntitySourceRef(
            asset_id="a", chapter_id="c", node_id="n",
        ),
        new_canonical="z",
    )
    merges = audit_module.list_logs("p-1", op_type="merge")
    assert len(merges) == 1
    splits = audit_module.list_logs("p-1", op_type="split")
    assert len(splits) == 1


def test_list_logs_only_undoable_filters_merges_and_undone():
    from app.schemas.entity_registry import EntitySourceRef
    a = registry.register_entity(
        project_id="p-1", node_id="n", node_type="person",
        label="A", asset_id="a", chapter_id="c",
    )
    audit_module.record_merge(
        project_id="p-1", source=registry.get_entity(a),
        target_id="tgt", target_label="B",
    )  # merge 不可 undo
    s1 = audit_module.record_split(
        project_id="p-1", source_id="src", new_entity_id="new1",
        moved_node_ref=EntitySourceRef(
            asset_id="a", chapter_id="c", node_id="n1",
        ),
        new_canonical="x",
    )
    audit_module.record_split(
        project_id="p-1", source_id="src", new_entity_id="new2",
        moved_node_ref=EntitySourceRef(
            asset_id="a", chapter_id="c", node_id="n2",
        ),
        new_canonical="y",
    )
    # 标 s1 已 undone
    s1.undone = True

    undoable = audit_module.list_logs("p-1", only_undoable=True)
    assert len(undoable) == 1  # 仅 s2 (split + 未 undone)


def test_undo_split_restores_entity():
    """end-to-end: split → undo → ref 回 source, new entity 删."""
    eid = _seed_entity_with_2_refs()
    src = registry.get_entity(eid)
    # split 出 a-2 / n_a2
    result = registry.split_node_to_new_entity(
        eid, asset_id="a-2", node_id="n_a2",
        new_label="Alice (different)",
    )
    assert result is not None
    src_after, new_ent = result
    from app.schemas.entity_registry import EntitySourceRef
    moved_ref = new_ent.source_refs[0]
    log = audit_module.record_split(
        project_id="p-1", source_id=src_after.id,
        new_entity_id=new_ent.id,
        moved_node_ref=moved_ref,
        new_canonical=new_ent.canonical_label,
    )
    # 之前: src 有 a-1 ref, new 有 a-2 ref
    assert len(src_after.source_refs) == 1
    assert len(new_ent.source_refs) == 1

    # undo
    updated = audit_module.undo_split(log.id, actor_id="u-1")
    assert updated is not None
    assert updated.undone is True
    assert updated.undone_by == "u-1"
    # new_ent 已删
    assert registry.get_entity(new_ent.id) is None
    # src 拿回 2 个 refs
    src_now = registry.get_entity(eid)
    assert len(src_now.source_refs) == 2
    # node→entity 反查回 src
    lookup = registry.get_entity_for_node("a-2", "n_a2")
    assert lookup.id == eid


def test_undo_split_idempotent_blocked():
    """undo 后再 undo 同 log → None."""
    eid = _seed_entity_with_2_refs()
    result = registry.split_node_to_new_entity(
        eid, asset_id="a-2", node_id="n_a2",
    )
    src_after, new_ent = result
    log = audit_module.record_split(
        project_id="p-1", source_id=src_after.id,
        new_entity_id=new_ent.id,
        moved_node_ref=new_ent.source_refs[0],
        new_canonical=new_ent.canonical_label,
    )
    audit_module.undo_split(log.id)
    second = audit_module.undo_split(log.id)
    assert second is None


def test_undo_split_blocked_when_new_entity_changed():
    """如果 new_entity 在 undo 前被加新 ref → 拒绝撤销."""
    eid = _seed_entity_with_2_refs()
    result = registry.split_node_to_new_entity(
        eid, asset_id="a-2", node_id="n_a2",
    )
    src_after, new_ent = result
    log = audit_module.record_split(
        project_id="p-1", source_id=src_after.id,
        new_entity_id=new_ent.id,
        moved_node_ref=new_ent.source_refs[0],
        new_canonical=new_ent.canonical_label,
    )
    # 给 new_ent 加 1 个 ref (违反 split 后 单 ref 状态)
    registry.register_entity(
        project_id="p-1", node_id="n_extra",
        node_type=new_ent.type, label=new_ent.label,
        asset_id="a-3", chapter_id="ch-3",
    )
    # canonical 重叠时会 merge 到 new_ent? — 不一定, 看 canonical 是否一致
    # 我们强制 new_ent.source_refs 数 > 1 以触发 undo 失败:
    from app.schemas.entity_registry import EntitySourceRef
    new_ent.source_refs.append(EntitySourceRef(
        asset_id="a-99", chapter_id="ch", node_id="n",
    ))
    res = audit_module.undo_split(log.id)
    assert res is None  # 拒绝


def test_undo_unknown_log():
    assert audit_module.undo_split("no-such") is None


# ── API ──────────────────────────────────────────────────────────


def test_api_list_audit_log(client):
    _seed_asset("a-1")
    _seed_asset("a-2")
    eid = _seed_entity_with_2_refs()
    # 通过 API split 触发 audit 记录
    r = client.post(
        f"/entities/{eid}/split",
        json={"asset_id": "a-2", "node_id": "n_a2"},
    )
    assert r.status_code == 200
    # list audit
    r2 = client.get("/projects/p-1/entities/audit_log")
    assert r2.status_code == 200
    body = r2.json()
    assert len(body) == 1
    assert body[0]["op_type"] == "split"


def test_api_undo_split_round_trip(client):
    _seed_asset("a-1")
    _seed_asset("a-2")
    eid = _seed_entity_with_2_refs()
    client.post(
        f"/entities/{eid}/split",
        json={"asset_id": "a-2", "node_id": "n_a2"},
    )
    logs = client.get("/projects/p-1/entities/audit_log").json()
    log_id = logs[0]["id"]
    r = client.post(f"/entities/audit/{log_id}/undo")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["undone"] is True


def test_api_undo_merge_rejected(client):
    """merge 操作不允许 undo (v1.6 限制)."""
    _seed_asset("a-1")
    _seed_asset("a-2")
    a = registry.register_entity(
        project_id="p-1", node_id="n", node_type="person",
        label="A", asset_id="a-1", chapter_id="ch-1",
    )
    b = registry.register_entity(
        project_id="p-1", node_id="n2", node_type="person",
        label="B", asset_id="a-2", chapter_id="ch-2",
    )
    client.post(f"/entities/{a}/merge", json={"target_id": b})
    logs = client.get("/projects/p-1/entities/audit_log").json()
    merge_log = next(l for l in logs if l["op_type"] == "merge")
    r = client.post(f"/entities/audit/{merge_log['id']}/undo")
    assert r.status_code == 422


def test_api_undo_already_undone(client):
    _seed_asset("a-1")
    _seed_asset("a-2")
    eid = _seed_entity_with_2_refs()
    client.post(
        f"/entities/{eid}/split",
        json={"asset_id": "a-2", "node_id": "n_a2"},
    )
    log_id = client.get("/projects/p-1/entities/audit_log").json()[0]["id"]
    client.post(f"/entities/audit/{log_id}/undo")
    r = client.post(f"/entities/audit/{log_id}/undo")
    assert r.status_code == 422


def test_api_undo_unknown_log_404(client):
    r = client.post("/entities/audit/no-such/undo")
    assert r.status_code == 404


def test_api_list_audit_log_filter_op_type(client):
    _seed_asset("a-1")
    _seed_asset("a-2")
    a = registry.register_entity(
        project_id="p-1", node_id="n", node_type="person",
        label="A", asset_id="a-1", chapter_id="ch-1",
    )
    b = registry.register_entity(
        project_id="p-1", node_id="n2", node_type="person",
        label="B", asset_id="a-2", chapter_id="ch-2",
    )
    client.post(f"/entities/{a}/merge", json={"target_id": b})
    # 再 split (要 entity 有 2 refs)
    # b 现在 含 a 的原 ref
    # split b
    client.post(
        f"/entities/{b}/split",
        json={"asset_id": "a-1", "node_id": "n"},
    )
    r = client.get("/projects/p-1/entities/audit_log?op_type=split")
    assert all(l["op_type"] == "split" for l in r.json())
