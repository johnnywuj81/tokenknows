"""T82 · KG assess 纯函数 (dedup / bidirect / isolated / metrics)."""

from __future__ import annotations

import pytest

from app.schemas.knowledge_graph import KGEdge, KGNode
from app.services.knowledge_graph.assess import (
    bidirect_contradicts,
    compute_assess_metrics,
    dedup_nodes,
    find_isolated_nodes,
)


def _node(
    nid: str, ntype: str = "person", label: str = "",
    im_user_id: str | None = None, events: list[str] | None = None,
    trust: float = 0.5,
) -> KGNode:
    properties = {}
    if im_user_id:
        properties["im_user_id"] = im_user_id
    return KGNode(
        id=nid, type=ntype, label=label or nid,  # type: ignore[arg-type]
        properties=properties,
        source_event_ids=events or [],
        trust_score=trust,
    )


def _edge(
    eid: str, source: str, target: str, etype: str = "mentions",
    events: list[str] | None = None,
) -> KGEdge:
    return KGEdge(
        id=eid, source=source, target=target, type=etype,  # type: ignore[arg-type]
        source_event_ids=events or [],
    )


# ─── dedup_nodes ──────────────────────────────────────────


def test_dedup_no_duplicates_returns_same():
    nodes = [_node("n_a", "person", "Alice"), _node("n_b", "person", "Bob")]
    edges = [_edge("e1", "n_a", "n_b")]
    out_nodes, out_edges, merged = dedup_nodes(nodes, edges)
    assert merged == 0
    assert len(out_nodes) == 2
    assert len(out_edges) == 1


def test_dedup_empty_inputs():
    nodes, edges, merged = dedup_nodes([], [])
    assert nodes == []
    assert edges == []
    assert merged == 0


def test_dedup_person_by_im_user_id():
    """同 im_user_id 即合并, 即便 label 不同 (Alice vs A. Liu)."""
    nodes = [
        _node("n_1", "person", "Alice", im_user_id="ou-alice", events=["e1"]),
        _node("n_2", "person", "A. Liu", im_user_id="ou-alice", events=["e2"]),
    ]
    edges = [_edge("e_x", "n_2", "n_other")]
    out_nodes, out_edges, merged = dedup_nodes(nodes, edges)
    assert merged == 1
    assert len(out_nodes) == 1
    # source_event_ids 合并
    assert set(out_nodes[0].source_event_ids) == {"e1", "e2"}
    # edge 重定向: n_2 → n_1
    assert out_edges[0].source == "n_1"


def test_dedup_concept_by_normalized_label():
    """非 person 节点按 normalized label 合并."""
    nodes = [
        _node("n_1", "concept", "JWT 迁移", events=["e1"]),
        _node("n_2", "concept", "jwt-迁移", events=["e2"]),  # 不同写法
    ]
    out_nodes, out_edges, merged = dedup_nodes(nodes, [])
    assert merged == 1
    assert len(out_nodes) == 1


def test_dedup_event_pr_normalized():
    """'PR #127' / 'PR#127' / 'pr-127' → 同一 event."""
    nodes = [
        _node("n_1", "event", "PR #127"),
        _node("n_2", "event", "PR#127"),
        _node("n_3", "event", "pr-127"),
    ]
    out_nodes, _, merged = dedup_nodes(nodes, [])
    assert merged == 2
    assert len(out_nodes) == 1


def test_dedup_different_types_not_merged():
    """同 label 但不同 type 不合并 (e.g. concept 'Alice' vs person 'Alice')."""
    nodes = [
        _node("n_1", "person", "Alice", im_user_id="ou-alice"),
        _node("n_2", "concept", "Alice"),  # 一个概念叫 "Alice" (edge case)
    ]
    out_nodes, _, merged = dedup_nodes(nodes, [])
    assert merged == 0
    assert len(out_nodes) == 2


def test_dedup_trust_score_max():
    """合并时 trust_score 取 max."""
    nodes = [
        _node("n_1", "concept", "JWT", trust=0.4),
        _node("n_2", "concept", "jwt", trust=0.9),
    ]
    out_nodes, _, merged = dedup_nodes(nodes, [])
    assert merged == 1
    assert out_nodes[0].trust_score == 0.9


def test_dedup_self_loop_dropped_after_merge():
    """合并后 source == target (自环) 应丢弃."""
    nodes = [
        _node("n_1", "person", "Alice", im_user_id="ou-alice"),
        _node("n_2", "person", "Alice 别名", im_user_id="ou-alice"),
        _node("n_3", "event", "PR"),
    ]
    edges = [
        _edge("e_loop", "n_1", "n_2"),  # 合并后 n_1 → n_1 自环
        _edge("e_ok", "n_3", "n_1"),
    ]
    _, out_edges, _ = dedup_nodes(nodes, edges)
    assert len(out_edges) == 1
    assert out_edges[0].id == "e_ok"


def test_dedup_edge_triple_dedup():
    """重定向后 (source, target, type) 同的边只保留一条."""
    nodes = [
        _node("n_1", "concept", "X"),
        _node("n_2", "concept", "x"),  # 合并到 n_1
        _node("n_3", "person", "P", im_user_id="ou-p"),
    ]
    edges = [
        _edge("e1", "n_3", "n_1", "mentions"),
        _edge("e2", "n_3", "n_2", "mentions"),  # 重定向后 (n_3, n_1, mentions) 重复
    ]
    _, out_edges, _ = dedup_nodes(nodes, edges)
    assert len(out_edges) == 1


# ─── bidirect_contradicts ─────────────────────────────────


def test_bidirect_contradicts_adds_reverse():
    edges = [_edge("e1", "a", "b", "contradicts")]
    out = bidirect_contradicts(edges)
    assert len(out) == 2
    ids = {e.id for e in out}
    assert "e1" in ids
    assert "rev_e1" in ids
    rev = next(e for e in out if e.id == "rev_e1")
    assert rev.source == "b" and rev.target == "a"
    assert rev.type == "contradicts"


def test_bidirect_skips_non_contradicts():
    edges = [
        _edge("e1", "a", "b", "depends_on"),
        _edge("e2", "a", "b", "authored_by"),
    ]
    out = bidirect_contradicts(edges)
    assert len(out) == 2


def test_bidirect_no_dup_if_reverse_already_exists():
    """LLM 主动给了双向 contradicts 时, 不再重复添加."""
    edges = [
        _edge("e1", "a", "b", "contradicts"),
        _edge("e2", "b", "a", "contradicts"),
    ]
    out = bidirect_contradicts(edges)
    assert len(out) == 2  # 不增


def test_bidirect_empty():
    assert bidirect_contradicts([]) == []


# ─── find_isolated_nodes ──────────────────────────────────


def test_isolated_all_connected():
    nodes = [_node("a"), _node("b"), _node("c")]
    edges = [_edge("e1", "a", "b"), _edge("e2", "b", "c")]
    assert find_isolated_nodes(nodes, edges) == []


def test_isolated_some_disconnected():
    nodes = [_node("a"), _node("b"), _node("c"), _node("d")]
    edges = [_edge("e1", "a", "b")]
    # c, d 孤立
    isolated = find_isolated_nodes(nodes, edges)
    assert set(isolated) == {"c", "d"}


def test_isolated_no_edges():
    nodes = [_node("a"), _node("b")]
    assert set(find_isolated_nodes(nodes, [])) == {"a", "b"}


# ─── compute_assess_metrics ───────────────────────────────


def test_metrics_empty_graph():
    m = compute_assess_metrics([], [], [], 0)
    assert m["coverage"] == 0.0
    assert m["citation_density"] == 0.0


def test_metrics_full_coverage():
    """所有节点都有 source_event_ids → coverage=1."""
    nodes = [_node("a", events=["e1"]), _node("b", events=["e2"])]
    m = compute_assess_metrics(nodes, [], [], 0)
    assert m["coverage"] == 1.0


def test_metrics_partial_coverage():
    nodes = [_node("a", events=["e1"]), _node("b")]
    m = compute_assess_metrics(nodes, [], [], 0)
    assert m["coverage"] == 0.5


def test_metrics_citation_density_capped():
    """单节点 7 events → citation_density 截到 1.0."""
    nodes = [_node("a", events=[f"e{i}" for i in range(7)])]
    m = compute_assess_metrics(nodes, [], [], 0)
    assert m["citation_density"] == 1.0


def test_metrics_slop_score_from_merge_count():
    """merged_count=2 + final=3 → orig=5 → slop=0.4."""
    nodes = [_node("a"), _node("b"), _node("c")]
    m = compute_assess_metrics(nodes, [], [], 2)
    assert m["slop_score"] == 0.4


def test_metrics_consistency_isolated_penalty():
    """4 节点 1 孤立 → consistency = 1 - 0.25 = 0.75."""
    nodes = [_node("a"), _node("b"), _node("c"), _node("d")]
    m = compute_assess_metrics(nodes, [], ["d"], 0)
    assert m["consistency_score"] == 0.75


# ─── 集成: 完整 assess 流程 ──────────────────────────────


def test_full_assess_pipeline():
    """模拟 LLM 输出含重复实体 + 单向 contradicts + 孤立节点."""
    nodes = [
        _node("n_alice", "person", "Alice", im_user_id="ou-a", events=["e1"]),
        _node("n_alice2", "person", "A. Liu", im_user_id="ou-a", events=["e2"]),  # dup
        _node("n_decision_a", "concept", "用 JWT", trust=0.7),
        _node("n_decision_b", "concept", "用 X-User-Id", trust=0.6),
        _node("n_isolated", "concept", "孤岛"),
    ]
    edges = [
        _edge("e1", "n_alice", "n_decision_a", "mentions"),
        _edge("e2", "n_decision_a", "n_decision_b", "contradicts"),
    ]

    # 1. dedup
    new_nodes, new_edges, merged = dedup_nodes(nodes, edges)
    assert merged == 1
    # 2. bidirect contradicts
    new_edges = bidirect_contradicts(new_edges)
    assert len(new_edges) == 3  # mentions + 双向 contradicts
    # 3. isolated
    isolated = find_isolated_nodes(new_nodes, new_edges)
    assert "n_isolated" in isolated
    # 4. metrics
    m = compute_assess_metrics(new_nodes, new_edges, isolated, merged)
    assert m["consistency_score"] == 0.75  # 4 节点 1 孤立
    assert m["slop_score"] > 0  # 因 merge
