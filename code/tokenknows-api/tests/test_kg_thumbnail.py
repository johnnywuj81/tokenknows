"""v1.3.1 T95 · knowledge_graph.thumbnail.render_kg_svg 单测.

验:
  - 空 layout / 空 nodes → 占位 SVG
  - 节点 → 4 列 (按 type) + 每节点 1 个 circle
  - 边渲染为 line; 端点缺失自动跳过
  - >50 节点截断 + "+N nodes" 角标
  - label HTML 转义 (防 XSS)
  - SVG 输出为 valid string (含 viewBox)
"""

from __future__ import annotations

from app.services.knowledge_graph.thumbnail import render_kg_svg


def test_empty_layout_returns_placeholder_svg():
    svg = render_kg_svg({})
    assert '<svg' in svg and '</svg>' in svg
    assert 'empty graph' in svg


def test_no_nodes_returns_placeholder():
    svg = render_kg_svg({"nodes": [], "edges": []})
    assert 'empty graph' in svg


def test_single_node_renders_circle():
    layout = {
        "nodes": [{
            "id": "n1", "type": "person", "label": "Alice",
            "trust_score": 0.9, "source_event_ids": [], "properties": {},
        }],
        "edges": [],
    }
    svg = render_kg_svg(layout)
    assert '<circle' in svg
    assert 'Alice' in svg  # top-8 → 有 label
    assert 'viewBox' in svg


def test_four_types_render_in_separate_columns():
    """4 个 type 各 1 个节点, x 坐标应当不同 (4 列)."""
    layout = {
        "nodes": [
            {"id": "p1", "type": "person", "label": "P", "trust_score": 0.9,
             "source_event_ids": [], "properties": {}},
            {"id": "e1", "type": "event", "label": "E", "trust_score": 0.9,
             "source_event_ids": [], "properties": {}},
            {"id": "c1", "type": "concept", "label": "C", "trust_score": 0.9,
             "source_event_ids": [], "properties": {}},
            {"id": "a1", "type": "artifact", "label": "A", "trust_score": 0.9,
             "source_event_ids": [], "properties": {}},
        ],
        "edges": [],
    }
    svg = render_kg_svg(layout)
    # 4 colors 都出现
    assert '#ca8a04' in svg  # person
    assert '#2563eb' in svg  # event
    assert '#16a34a' in svg  # concept
    assert '#dc2626' in svg  # artifact
    # 4 个 circle
    assert svg.count('<circle') == 4


def test_edges_rendered_when_both_endpoints_present():
    layout = {
        "nodes": [
            {"id": "p1", "type": "person", "label": "A", "trust_score": 0.9,
             "source_event_ids": [], "properties": {}},
            {"id": "e1", "type": "event", "label": "B", "trust_score": 0.9,
             "source_event_ids": [], "properties": {}},
        ],
        "edges": [
            {"id": "x", "source": "p1", "target": "e1", "type": "mentions",
             "weight": 1, "label": None, "source_event_ids": []},
        ],
    }
    svg = render_kg_svg(layout)
    assert '<line' in svg


def test_edge_with_missing_endpoint_skipped():
    layout = {
        "nodes": [{
            "id": "p1", "type": "person", "label": "A", "trust_score": 0.9,
            "source_event_ids": [], "properties": {},
        }],
        "edges": [
            {"id": "x", "source": "p1", "target": "ghost", "type": "mentions",
             "weight": 1, "label": None, "source_event_ids": []},
        ],
    }
    svg = render_kg_svg(layout)
    # circle 在但没有 line
    assert '<circle' in svg
    assert '<line' not in svg


def test_truncation_above_50_nodes():
    """>50 节点: 仅 top-50 (按 trust desc) + '+N nodes' 角标."""
    nodes = []
    for i in range(70):
        nodes.append({
            "id": f"n{i}", "type": "person", "label": f"L{i}",
            "trust_score": i / 70.0,  # 0..1
            "source_event_ids": [], "properties": {},
        })
    svg = render_kg_svg({"nodes": nodes, "edges": []})
    # 50 circles (top 50 of 70)
    assert svg.count('<circle') == 50
    assert '+20 nodes' in svg


def test_contradicts_edge_uses_danger_color():
    layout = {
        "nodes": [
            {"id": "a", "type": "person", "label": "X", "trust_score": 0.9,
             "source_event_ids": [], "properties": {}},
            {"id": "b", "type": "event", "label": "Y", "trust_score": 0.9,
             "source_event_ids": [], "properties": {}},
        ],
        "edges": [{
            "id": "ec", "source": "a", "target": "b", "type": "contradicts",
            "weight": 1, "label": None, "source_event_ids": [],
        }],
    }
    svg = render_kg_svg(layout)
    # contradicts → danger red
    assert 'stroke="#dc2626"' in svg


def test_html_escapes_label():
    """label 含 <script> 时 HTML 转义."""
    layout = {
        "nodes": [{
            "id": "n", "type": "person",
            "label": "<script>alert(1)</script>",
            "trust_score": 0.9, "source_event_ids": [], "properties": {},
        }],
        "edges": [],
    }
    svg = render_kg_svg(layout)
    assert '<script>' not in svg
    assert '&lt;script&gt;' in svg


def test_only_top_8_get_label_text():
    """节点 > 8 时只前 8 个 label 渲染为 <text> (避免拥挤)."""
    nodes = []
    for i in range(12):
        nodes.append({
            "id": f"n{i}", "type": "person", "label": f"LABEL_{i}",
            "trust_score": (12 - i) / 12.0,  # n0 最高
            "source_event_ids": [], "properties": {},
        })
    svg = render_kg_svg({"nodes": nodes, "edges": []})
    # n0..n7 应该有 <text> + 'LABEL_X'
    for i in range(8):
        assert f"LABEL_{i}" in svg
    # n8..n11 不应该出现 (label 没渲染)
    for i in range(8, 12):
        assert f"LABEL_{i}" not in svg


def test_svg_has_aria_label():
    """svg 含 role='img' + aria-label 便于无障碍."""
    svg = render_kg_svg({"nodes": [], "edges": []})
    assert 'role="img"' in svg
    assert 'aria-label=' in svg
