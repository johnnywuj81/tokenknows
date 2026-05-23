"""v2.0 T117 · MCP server tools 单测.

Backend HTTP 用 fake client mock; 验证 MCP tool 参数 → backend payload 正确.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mcp_env(monkeypatch: pytest.MonkeyPatch):
    """每个 test 设 default project + mock client."""
    monkeypatch.setenv("TOKENKNOWS_DEFAULT_PROJECT", "p-test")
    from mcp_server import client as client_mod
    fake = MagicMock()
    fake.post = AsyncMock()
    fake.get = AsyncMock()
    client_mod.set_client(fake)
    yield fake
    client_mod.set_client(None)  # type: ignore[arg-type]


# ── submit_session_events ────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_events_uses_default_project(mcp_env):
    mcp_env.post.return_value = {"ingested": 2, "skipped": 0}
    from mcp_server.server import submit_session_events
    res = await submit_session_events(events=[
        {"content": "用户问 KG demo 怎么用", "author_name": "user"},
        {"content": "Claude 回答 demo URL", "author_name": "Claude"},
    ])
    assert res["ingested"] == 2
    assert res["project_id"] == "p-test"
    # 检查 backend POST 被调
    mcp_env.post.assert_called_once()
    url, kwargs = mcp_env.post.call_args.args[0], mcp_env.post.call_args.kwargs
    assert url == "/api/v1/projects/p-test/events"
    body = kwargs["json"]
    assert len(body["events"]) == 2
    # event_type 默认值
    assert body["events"][0]["event_type"] == "ai_conversation_turn"
    # source_type 默认 claude_code
    assert body["events"][0]["source_type"] == "claude_code"
    # content_hash 自动计算
    assert len(body["events"][0]["content_hash"]) == 64


@pytest.mark.asyncio
async def test_submit_events_explicit_project(mcp_env):
    mcp_env.post.return_value = {"ingested": 1, "skipped": 0}
    from mcp_server.server import submit_session_events
    res = await submit_session_events(
        events=[{"content": "x"}], project_id="p-custom",
    )
    assert res["project_id"] == "p-custom"
    url = mcp_env.post.call_args.args[0]
    assert "p-custom" in url


@pytest.mark.asyncio
async def test_submit_events_cowork_source(mcp_env):
    mcp_env.post.return_value = {"ingested": 1, "skipped": 0}
    from mcp_server.server import submit_session_events
    await submit_session_events(events=[
        {"content": "cowork msg", "source_type": "claude_cowork"},
    ])
    body = mcp_env.post.call_args.kwargs["json"]
    assert body["events"][0]["source_type"] == "claude_cowork"


@pytest.mark.asyncio
async def test_submit_events_no_project_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TOKENKNOWS_DEFAULT_PROJECT", raising=False)
    from mcp_server.server import submit_session_events
    with pytest.raises(ValueError, match="未指定 project_id"):
        await submit_session_events(events=[{"content": "x"}])


@pytest.mark.asyncio
async def test_submit_events_max_100(mcp_env):
    mcp_env.post.return_value = {"ingested": 100, "skipped": 0}
    from mcp_server.server import submit_session_events
    huge = [{"content": f"event {i}"} for i in range(200)]
    await submit_session_events(events=huge)
    body = mcp_env.post.call_args.kwargs["json"]
    assert len(body["events"]) == 100  # 截断


# ── distill_document ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_distill_kg(mcp_env):
    mcp_env.post.return_value = {
        "id": "asset-x", "status": "generating", "title": "知识图谱 · ...",
    }
    from mcp_server.server import distill_document
    res = await distill_document(document_type="knowledge_graph")
    assert res["asset_id"] == "asset-x"
    assert res["status"] == "generating"
    assert "view_url" in res
    url = mcp_env.post.call_args.args[0]
    body = mcp_env.post.call_args.kwargs["json"]
    assert url == "/api/v1/projects/p-test/assets/generate"
    assert body["type"] == "knowledge_graph"


@pytest.mark.asyncio
async def test_distill_with_model_override(mcp_env):
    mcp_env.post.return_value = {"id": "x", "status": "generating", "title": "t"}
    from mcp_server.server import distill_document
    await distill_document(document_type="weekly_report", model="gpt-4o")
    body = mcp_env.post.call_args.kwargs["json"]
    assert body["model_override"] == "gpt-4o"


# ── list / get assets ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_assets_filters(mcp_env):
    mcp_env.get.return_value = {
        "data": [
            {
                "id": "a1", "type": "knowledge_graph", "title": "KG",
                "status": "draft", "current_version": 1,
                "updated_at": "2026-01-01T00:00:00Z",
                "metrics": {"coverage": 0.9},
                "kg_summary": {"node_count": 5, "edge_count": 3, "thumbnail_svg": "..."},
            },
        ],
        "meta": {"total": 1},
    }
    from mcp_server.server import list_assets
    res = await list_assets(asset_type="knowledge_graph", limit=5)
    assert res["total"] == 1
    item = res["items"][0]
    assert item["id"] == "a1"
    # kg_summary 简化 (去掉 thumbnail)
    assert "thumbnail_svg" not in item["kg_summary"]
    # query params 透传
    params = mcp_env.get.call_args.kwargs["params"]
    assert params["type"] == "knowledge_graph"
    assert params["limit"] == 5


@pytest.mark.asyncio
async def test_get_asset(mcp_env):
    mcp_env.get.return_value = {
        "id": "a1", "type": "weekly_report", "title": "W21",
        "status": "draft", "current_version": 1, "approval_state": "pending",
        "metrics": None, "kg_summary": None,
        "updated_at": "2026-01-01T00:00:00Z",
    }
    from mcp_server.server import get_asset
    a = await get_asset("a1")
    assert a["status"] == "draft"


@pytest.mark.asyncio
async def test_get_asset_chapters_kg_simplifies_layout(mcp_env):
    mcp_env.get.return_value = [
        {
            "id": "ch1", "title": "Graph", "order_index": 0, "content": "# md",
            "approval_state": "pending",
            "layout": {
                "nodes": [{"id": "n1"}],
                "edges": [],
                "thumbnail_svg": "<svg>large</svg>",
                "thumbnail_png_b64": "iVBOR...",
            },
        },
    ]
    from mcp_server.server import get_asset_chapters
    chs = await get_asset_chapters("a1")
    assert len(chs) == 1
    # kg_layout 字段只含 nodes/edges 不含 thumbnail
    assert "thumbnail_svg" not in chs[0].get("kg_layout", {})
    assert chs[0]["kg_layout"]["nodes"] == [{"id": "n1"}]


# ── search_entity ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_entity(mcp_env):
    mcp_env.get.return_value = [
        {
            "id": "ent_1", "type": "person", "label": "Alice",
            "aliases": ["alice"], "asset_count": 3,
            "source_refs": [{"asset_id": "a1"}, {"asset_id": "a2"}],
        },
    ]
    from mcp_server.server import search_entity
    res = await search_entity(query="alice", entity_type="person", min_assets=2)
    assert len(res) == 1
    assert res[0]["label"] == "Alice"
    params = mcp_env.get.call_args.kwargs["params"]
    assert params["q"] == "alice"
    assert params["type"] == "person"
    assert params["min_assets"] == 2


# ── resource ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_asset_resource(mcp_env):
    mcp_env.get.side_effect = [
        # asset
        {
            "id": "a1", "type": "weekly_report", "title": "W21",
            "status": "draft", "current_version": 1,
        },
        # chapters
        [
            {"id": "c1", "title": "进展", "order_index": 0, "content": "项目稳步推进"},
            {"id": "c2", "title": "Bug", "order_index": 1, "content": "修了 5 个"},
        ],
    ]
    from mcp_server.server import asset_resource
    md = await asset_resource("a1")
    assert "# W21" in md
    assert "## 进展" in md
    assert "## Bug" in md
    assert "项目稳步推进" in md


# ── prompt ───────────────────────────────────────────────────────


def test_distill_session_prompt():
    from mcp_server.server import distill_session
    text = distill_session("adr")
    assert "adr" in text
    assert "submit_session_events" in text
    assert "distill_document" in text
