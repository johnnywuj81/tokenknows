"""T84 · KnowledgeGraph pipeline 3-stage 集成测试.

覆盖 4 fixture:
- small_happy: 5 events + 5 nodes + 3 edges 正常流水线
- disconnected: 含孤立节点 (assess 标记)
- parse_error: outline stage LLM 返无效 JSON → 兜底 contributors_only
- dedup: 同 im_user_id 的 person 节点被合并

mock LLM router; 不调真 API.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.asset import Asset
from app.schemas.generation import GenerateAssetRequest
from app.services import generation_service, skill_service


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    skill_service.reset_registry_for_tests()
    generation_service._assets.clear()
    generation_service._chapters.clear()
    generation_service._progress.clear()
    generation_service._evidence_by_chapter.clear()
    generation_service._sse_queues.clear()
    yield new_store


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_kg_asset(asset_id: str = "a-kg", project_id: str = "p-kg") -> Asset:
    asset = Asset(
        id=asset_id, project_id=project_id, type="knowledge_graph",
        title="JWT 迁移知识图谱",
        status="generating", current_version=1, template_id=None,
        created_by="u", created_at=_now(), updated_at=_now(),
    )
    generation_service._assets[asset_id] = asset
    generation_service._progress[asset_id] = generation_service._initial_progress(asset_id)
    return asset


def _seed_events_in_collect(
    asset_id: str, events: list[dict]
) -> None:
    """把 events 列表塞进 collect stage metadata, 模拟 collect 已跑完."""
    progress = generation_service._progress[asset_id]
    collect_idx = generation_service._stage_index(progress, "collect")
    progress.stages[collect_idx].metadata = {"events": events}


class _KGRouter:
    """Mock router: outline LLM 调 1 次, content LLM 调 1 次, 顺序返响应."""

    def __init__(
        self, outline_response: str, content_response: str
    ) -> None:
        self.outline_response = outline_response
        self.content_response = content_response
        self.calls: list[dict] = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        sys_prompt = kwargs.get("messages", [None])[0]
        text = sys_prompt.content if sys_prompt else ""
        if "节点骨架" in text or "实体抽取器" in text:
            payload = self.outline_response
        else:
            payload = self.content_response
        return type("Resp", (), {
            "text": payload,
            "provider": "anthropic",
            "model_used": "claude",
            "usage": {"prompt_tokens": 100, "completion_tokens": 200},
            "fallback_used": False,
            "latency_ms": 50,
        })()


def _events_fixture() -> list[dict]:
    """5 events 跨 2 contributors + 2 concepts."""
    return [
        {
            "id": "evt-1", "type": "github_pr", "trust_score": 0.9,
            "author": {"im_user_id": "ou-alice", "name": "Alice"},
            "payload": {"title": "PR #127 JWT 迁移"},
            "source_ref": "github.com/x/repo/pull/127",
        },
        {
            "id": "evt-2", "type": "im_message", "trust_score": 0.7,
            "author": {"im_user_id": "ou-bob", "name": "Bob"},
            "payload": {"title": "讨论 JWT 算法"},
            "source_ref": "feishu chat:oc-x",
        },
        {
            "id": "evt-3", "type": "github_pr", "trust_score": 0.8,
            "author": {"im_user_id": "ou-alice", "name": "Alice"},
            "payload": {"title": "PR #128 取消 X-User-Id"},
            "source_ref": "github.com/x/repo/pull/128",
        },
        {
            "id": "evt-4", "type": "incident", "trust_score": 0.95,
            "author": {"im_user_id": "ou-carol", "name": "Carol"},
            "payload": {"title": "登录大量 401"},
        },
        {
            "id": "evt-5", "type": "doc_change", "trust_score": 0.6,
            "author": {"im_user_id": "ou-bob", "name": "Bob"},
            "payload": {"title": "更新 ADR-007"},
        },
    ]


# ─── 4 fixture pipeline tests ─────────────────────────────


@pytest.mark.asyncio
async def test_kg_pipeline_small_happy_path(monkeypatch) -> None:
    """5 events → outline 5 nodes → content 3 edges → assess metrics 完整."""
    asset = _seed_kg_asset()
    _seed_events_in_collect(asset.id, _events_fixture())

    outline_resp = json.dumps({
        "nodes": [
            {"id": "n_alice", "type": "person", "label": "Alice",
             "properties": {"im_user_id": "ou-alice"},
             "source_event_ids": ["evt-1", "evt-3"], "trust_score": 0.85},
            {"id": "n_bob", "type": "person", "label": "Bob",
             "properties": {"im_user_id": "ou-bob"},
             "source_event_ids": ["evt-2", "evt-5"], "trust_score": 0.75},
            {"id": "n_jwt", "type": "concept", "label": "JWT 迁移",
             "source_event_ids": ["evt-1", "evt-2"], "trust_score": 0.8},
            {"id": "n_pr127", "type": "event", "label": "PR #127",
             "source_event_ids": ["evt-1"], "trust_score": 0.8},
            {"id": "n_incident", "type": "event", "label": "登录 401 故障",
             "source_event_ids": ["evt-4"], "trust_score": 0.9},
        ],
    })
    content_resp = json.dumps({
        "edges": [
            {"id": "e1", "source": "n_pr127", "target": "n_alice",
             "type": "authored_by", "label": "PR #127 by Alice",
             "weight": 3, "source_event_ids": ["evt-1"]},
            {"id": "e2", "source": "n_pr127", "target": "n_jwt",
             "type": "mentions", "label": "PR 讨论 JWT",
             "weight": 2, "source_event_ids": ["evt-1"]},
            {"id": "e3", "source": "n_incident", "target": "n_jwt",
             "type": "caused_by", "label": "401 故障由 JWT 配置错引发",
             "weight": 4, "source_event_ids": ["evt-4"]},
        ],
        "node_summaries": [
            {"node_id": "n_jwt", "summary": "JWT 迁移决策"},
        ],
    })

    fake_router = _KGRouter(outline_resp, content_resp)
    monkeypatch.setattr(generation_service, "get_router",
                        lambda: asyncio.sleep(0, result=fake_router))

    req = GenerateAssetRequest(type="knowledge_graph", time_window="近30天")

    # outline
    out_result = await generation_service._stage_outline_knowledge_graph(
        asset.id, req
    )
    assert out_result["node_count"] == 5
    assert out_result["method"] == "llm"
    # 把 outline metadata 塞进 progress (模拟 _run_stage 行为)
    progress = generation_service._progress[asset.id]
    outline_idx = generation_service._stage_index(progress, "outline")
    progress.stages[outline_idx].metadata = out_result

    # content
    ctn_result = await generation_service._stage_content_knowledge_graph(
        asset.id, req
    )
    assert ctn_result["chapters_created"] == 1
    assert ctn_result["edges_added"] == 3
    assert ctn_result["node_count"] == 5

    # 验 chapter 真的写了
    chapters = generation_service._chapters[asset.id]
    assert len(chapters) == 1
    chapter = chapters[0]
    assert chapter.title == "实体关系图谱"
    assert "node:n_alice" in chapter.content
    # layout 有 nodes + edges
    layout = chapter.layout
    assert layout["schema_version"] == "kg.v1"
    assert len(layout["nodes"]) == 5
    assert len(layout["edges"]) == 3
    # node summary 已 merge (n_jwt 有 summary)
    jwt_node = next(n for n in layout["nodes"] if n["id"] == "n_jwt")
    assert jwt_node["summary"] == "JWT 迁移决策"

    # assess
    assess_result = await generation_service._stage_assess_knowledge_graph(
        asset.id, req
    )
    assert assess_result["node_count"] == 5
    # 3 edges, 无 contradicts 不补反向
    assert assess_result["edge_count"] == 3
    # asset.metrics 已写
    assert asset.metrics is not None
    assert asset.metrics.coverage > 0
    assert asset.metrics.consistency_score is not None


@pytest.mark.asyncio
async def test_kg_pipeline_disconnected_node_warned(monkeypatch) -> None:
    """含孤立节点 (no in/out edges) → assess 标记."""
    asset = _seed_kg_asset(asset_id="a-disc")
    _seed_events_in_collect(asset.id, _events_fixture())

    outline_resp = json.dumps({
        "nodes": [
            {"id": "n_a", "type": "person", "label": "Alice",
             "properties": {"im_user_id": "ou-a"},
             "source_event_ids": ["evt-1"], "trust_score": 0.8},
            {"id": "n_b", "type": "event", "label": "PR",
             "source_event_ids": ["evt-1"], "trust_score": 0.7},
            {"id": "n_lonely", "type": "concept", "label": "孤岛概念",
             "source_event_ids": ["evt-5"], "trust_score": 0.5},
        ],
    })
    content_resp = json.dumps({
        "edges": [
            {"id": "e1", "source": "n_b", "target": "n_a",
             "type": "authored_by", "weight": 1, "source_event_ids": ["evt-1"]},
        ],
        "node_summaries": [],
    })
    fake = _KGRouter(outline_resp, content_resp)
    monkeypatch.setattr(generation_service, "get_router",
                        lambda: asyncio.sleep(0, result=fake))

    req = GenerateAssetRequest(type="knowledge_graph", time_window="近30天")
    out = await generation_service._stage_outline_knowledge_graph(asset.id, req)
    progress = generation_service._progress[asset.id]
    progress.stages[generation_service._stage_index(progress, "outline")].metadata = out
    await generation_service._stage_content_knowledge_graph(asset.id, req)
    assess = await generation_service._stage_assess_knowledge_graph(asset.id, req)

    assert assess["isolated_count"] == 1
    # n_lonely 应被标
    chapter = generation_service._chapters[asset.id][0]
    # consistency_score < 1
    assert asset.metrics.consistency_score is not None
    assert asset.metrics.consistency_score < 1.0


@pytest.mark.asyncio
async def test_kg_pipeline_outline_parse_error_fallback(monkeypatch) -> None:
    """outline LLM 返无效 JSON → 兜底仅 contributors 节点; 仍可继续 content stage."""
    asset = _seed_kg_asset(asset_id="a-parse-err")
    _seed_events_in_collect(asset.id, _events_fixture())

    # outline 故意返坏 JSON
    fake = _KGRouter(
        outline_response="not a valid JSON {{{",
        content_response=json.dumps({"edges": [], "node_summaries": []}),
    )
    monkeypatch.setattr(generation_service, "get_router",
                        lambda: asyncio.sleep(0, result=fake))

    req = GenerateAssetRequest(type="knowledge_graph", time_window="近30天")
    out = await generation_service._stage_outline_knowledge_graph(asset.id, req)
    assert out["method"] == "fallback_contributors_only"
    # 3 个 contributors (alice/bob/carol) → 3 个 person 节点
    assert out["node_count"] == 3

    # content 仍能跑 (返空 edges)
    progress = generation_service._progress[asset.id]
    progress.stages[generation_service._stage_index(progress, "outline")].metadata = out
    ctn = await generation_service._stage_content_knowledge_graph(asset.id, req)
    assert ctn["chapters_created"] == 1


@pytest.mark.asyncio
async def test_kg_pipeline_dedup_in_assess(monkeypatch) -> None:
    """outline 出同 im_user_id 重复 person → assess 合并."""
    asset = _seed_kg_asset(asset_id="a-dedup")
    _seed_events_in_collect(asset.id, _events_fixture())

    # outline 故意给 2 个 alice (不同 id, 同 im_user_id)
    outline_resp = json.dumps({
        "nodes": [
            {"id": "n_alice1", "type": "person", "label": "Alice",
             "properties": {"im_user_id": "ou-alice"},
             "source_event_ids": ["evt-1"], "trust_score": 0.8},
            {"id": "n_alice2", "type": "person", "label": "A. Liu",
             "properties": {"im_user_id": "ou-alice"},
             "source_event_ids": ["evt-3"], "trust_score": 0.7},
            {"id": "n_bob", "type": "person", "label": "Bob",
             "properties": {"im_user_id": "ou-bob"},
             "source_event_ids": ["evt-2"], "trust_score": 0.7},
        ],
    })
    content_resp = json.dumps({
        "edges": [
            {"id": "e1", "source": "n_alice1", "target": "n_bob",
             "type": "mentions", "weight": 1, "source_event_ids": ["evt-1"]},
        ],
        "node_summaries": [],
    })
    fake = _KGRouter(outline_resp, content_resp)
    monkeypatch.setattr(generation_service, "get_router",
                        lambda: asyncio.sleep(0, result=fake))

    req = GenerateAssetRequest(type="knowledge_graph", time_window="近30天")
    # outline 中已可能 dedup (outline 内调一次 dedup); 但 assess 是最终保障
    out = await generation_service._stage_outline_knowledge_graph(asset.id, req)
    progress = generation_service._progress[asset.id]
    progress.stages[generation_service._stage_index(progress, "outline")].metadata = out
    await generation_service._stage_content_knowledge_graph(asset.id, req)
    assess = await generation_service._stage_assess_knowledge_graph(asset.id, req)

    # 3 个原始 → 合并到 2 个 person (alice + bob)
    # 注: dedup 已在 outline stage 完成 (防止 content prompt 看到重复 id);
    # 所以 assess 时 merged_count 可能为 0, 但 node_count 必为 2.
    assert assess["node_count"] == 2
    # 验 alice 节点确实合并了 evt-1 和 evt-3 两个 source_event_ids
    chapter = generation_service._chapters[asset.id][0]
    alice_node = next(
        n for n in chapter.layout["nodes"]
        if n.get("properties", {}).get("im_user_id") == "ou-alice"
    )
    assert set(alice_node["source_event_ids"]) == {"evt-1", "evt-3"}
