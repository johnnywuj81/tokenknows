"""T81 · KnowledgeGraph schema 校验.

覆盖:
- AssetType Literal 含 knowledge_graph
- KGNodeType / KGEdgeType 边界
- KGNode / KGEdge 字段校验
- KnowledgeGraphLayout default + roundtrip
- settings.task_provider / task_model 含 knowledge_graph
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.schemas.asset import AssetType
from app.schemas.knowledge_graph import (
    KGContentLLMOutput,
    KGEdge,
    KGLayoutHints,
    KGNode,
    KGNodeSummary,
    KGOutlineLLMOutput,
    KGSpanAnchor,
    KnowledgeGraphLayout,
)


# ─── AssetType 扩展 ───────────────────────────────────────


def test_asset_type_includes_knowledge_graph():
    """AssetType Literal 应含 knowledge_graph."""
    valid = AssetType.__args__  # type: ignore[attr-defined]
    assert "knowledge_graph" in valid
    # 既有 6 种保留
    for legacy in [
        "weekly_report", "tech_design", "adr", "incident", "book", "agent_skill"
    ]:
        assert legacy in valid


# ─── KGNode 校验 ──────────────────────────────────────────


def test_kg_node_all_types_valid():
    for t in ["person", "event", "concept", "artifact"]:
        n = KGNode(id="n_x", type=t, label="x")  # type: ignore[arg-type]
        assert n.type == t


def test_kg_node_invalid_type_rejected():
    with pytest.raises(ValidationError):
        KGNode(id="n_x", type="alien", label="x")  # type: ignore[arg-type]


def test_kg_node_id_max_length():
    with pytest.raises(ValidationError):
        KGNode(id="n_" + "x" * 100, type="person", label="a")


def test_kg_node_label_required():
    with pytest.raises(ValidationError):
        KGNode(id="n_x", type="person", label="")


def test_kg_node_trust_score_bounded():
    with pytest.raises(ValidationError):
        KGNode(id="n_x", type="person", label="a", trust_score=1.5)
    with pytest.raises(ValidationError):
        KGNode(id="n_x", type="person", label="a", trust_score=-0.1)


def test_kg_node_defaults():
    n = KGNode(id="n_x", type="person", label="Alice")
    assert n.summary is None
    assert n.properties == {}
    assert n.source_event_ids == []
    assert n.trust_score == 0.5
    assert n.span_anchor is None


def test_kg_span_anchor_negative_offset_rejected():
    with pytest.raises(ValidationError):
        KGSpanAnchor(char_offset=-1)


# ─── KGEdge 校验 ──────────────────────────────────────────


def test_kg_edge_all_types_valid():
    for t in [
        "authored_by", "mentions", "depends_on", "contradicts",
        "caused_by", "related_to",
    ]:
        e = KGEdge(
            id=f"e_{t}", source="a", target="b", type=t,  # type: ignore[arg-type]
        )
        assert e.type == t


def test_kg_edge_invalid_type_rejected():
    with pytest.raises(ValidationError):
        KGEdge(id="e_x", source="a", target="b", type="bad")  # type: ignore[arg-type]


def test_kg_edge_weight_bounded():
    with pytest.raises(ValidationError):
        KGEdge(
            id="e_x", source="a", target="b", type="mentions", weight=0
        )
    with pytest.raises(ValidationError):
        KGEdge(
            id="e_x", source="a", target="b", type="mentions", weight=6
        )


def test_kg_edge_defaults():
    e = KGEdge(id="e_1", source="a", target="b", type="authored_by")
    assert e.label is None
    assert e.weight == 1
    assert e.source_event_ids == []


# ─── KnowledgeGraphLayout ─────────────────────────────────


def test_layout_defaults():
    layout = KnowledgeGraphLayout()
    assert layout.schema_version == "kg.v1"
    assert layout.nodes == []
    assert layout.edges == []
    assert layout.layout_hints.algorithm == "dagre"
    assert layout.layout_hints.rankdir == "LR"
    assert layout.parse_error is None


def test_layout_roundtrip_json():
    layout = KnowledgeGraphLayout(
        nodes=[
            KGNode(
                id="n_alice", type="person", label="Alice",
                properties={"im_user_id": "ou-alice"},
                source_event_ids=["evt-1", "evt-2"],
                trust_score=0.85,
                span_anchor=KGSpanAnchor(char_offset=42),
            ),
            KGNode(
                id="n_pr127", type="event", label="PR #127 JWT 迁移",
                summary="Alice 提交了 JWT 迁移 PR",
                source_event_ids=["evt-1"],
            ),
        ],
        edges=[
            KGEdge(
                id="e_1", source="n_pr127", target="n_alice",
                type="authored_by",
                label="PR #127 由 @alice 合并",
                weight=3,
                source_event_ids=["evt-1"],
            ),
        ],
        layout_hints=KGLayoutHints(algorithm="dagre", rankdir="LR"),
    )

    dumped = layout.model_dump_json()
    parsed = json.loads(dumped)
    assert parsed["schema_version"] == "kg.v1"
    assert len(parsed["nodes"]) == 2
    assert parsed["nodes"][0]["span_anchor"]["char_offset"] == 42

    # roundtrip via Pydantic
    layout2 = KnowledgeGraphLayout.model_validate(parsed)
    assert len(layout2.nodes) == 2
    assert layout2.nodes[0].id == "n_alice"
    assert layout2.edges[0].weight == 3


def test_layout_with_parse_error_fallback():
    """LLM parse 失败时存原始 raw_output 供调试."""
    layout = KnowledgeGraphLayout(
        parse_error="json.JSONDecodeError: line 5",
        raw_output='{"nodes": [{"id":',
    )
    assert layout.parse_error is not None
    assert layout.nodes == []  # 节点空


def test_layout_raw_output_max_length():
    """raw_output 限 4000 字符避免 chapter.layout 爆炸."""
    with pytest.raises(ValidationError):
        KnowledgeGraphLayout(raw_output="x" * 5000)


# ─── LLM 输出 DTO ────────────────────────────────────────


def test_kg_outline_llm_output_empty_default():
    out = KGOutlineLLMOutput()
    assert out.nodes == []


def test_kg_outline_llm_output_parse():
    raw_json = {
        "nodes": [
            {"id": "n_a", "type": "person", "label": "Alice", "source_event_ids": []},
            {"id": "n_b", "type": "event", "label": "PR", "source_event_ids": ["e1"]},
        ]
    }
    out = KGOutlineLLMOutput.model_validate(raw_json)
    assert len(out.nodes) == 2
    assert out.nodes[1].type == "event"


def test_kg_content_llm_output_parse():
    raw_json = {
        "edges": [
            {"id": "e_1", "source": "n_a", "target": "n_b",
             "type": "authored_by"},
        ],
        "node_summaries": [
            {"node_id": "n_a", "summary": "Alice 是 owner"},
        ],
    }
    out = KGContentLLMOutput.model_validate(raw_json)
    assert len(out.edges) == 1
    assert out.node_summaries[0].node_id == "n_a"


# ─── settings.task_provider/task_model ───────────────────


def test_settings_task_provider_knowledge_graph():
    from app.config.settings import get_settings
    s = get_settings()
    p = s.task_provider("knowledge_graph")
    m = s.task_model("knowledge_graph")
    # 默认 anthropic / claude-sonnet-4-5; 用户可 env override
    assert isinstance(p, str) and len(p) > 0
    assert isinstance(m, str) and len(m) > 0


def test_settings_unknown_task_still_raises():
    """v1.2 加 knowledge_graph 后, 其他未知 task 仍报错."""
    from app.config.settings import get_settings
    s = get_settings()
    with pytest.raises(ValueError):
        s.task_provider("unknown_task_xyz")
