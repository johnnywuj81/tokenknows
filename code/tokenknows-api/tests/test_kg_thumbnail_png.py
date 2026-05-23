"""v1.5 T100 · thumbnail_png 单测.

验:
  - 空 layout → 占位 PNG (有效 PNG bytes)
  - 节点渲染 → PNG bytes 非空, magic byte 'PNG'
  - render_kg_png_b64 输出 valid base64, 解码后等于 PNG bytes
  - 大图截断 (>50 节点) 不崩
  - layout 异常 (None/缺 nodes) silent 返回
"""

from __future__ import annotations

import base64

from app.services.knowledge_graph.thumbnail_png import (
    render_kg_png,
    render_kg_png_b64,
)


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_empty_layout_returns_placeholder_png():
    png = render_kg_png({"nodes": [], "edges": []})
    assert png is not None
    assert png.startswith(_PNG_MAGIC)


def test_single_node_renders_png():
    layout = {
        "nodes": [{
            "id": "n1", "type": "person", "label": "Alice",
            "trust_score": 0.9, "source_event_ids": [], "properties": {},
        }],
        "edges": [],
    }
    png = render_kg_png(layout)
    assert png is not None
    assert png.startswith(_PNG_MAGIC)
    assert len(png) > 100  # non-trivial size


def test_four_types_render_without_error():
    layout = {
        "nodes": [
            {"id": "p", "type": "person", "label": "P", "trust_score": 0.9,
             "source_event_ids": [], "properties": {}},
            {"id": "e", "type": "event", "label": "E", "trust_score": 0.9,
             "source_event_ids": [], "properties": {}},
            {"id": "c", "type": "concept", "label": "C", "trust_score": 0.9,
             "source_event_ids": [], "properties": {}},
            {"id": "a", "type": "artifact", "label": "A", "trust_score": 0.9,
             "source_event_ids": [], "properties": {}},
        ],
        "edges": [{
            "id": "x", "source": "p", "target": "e", "type": "mentions",
            "weight": 1, "label": None, "source_event_ids": [],
        }],
    }
    png = render_kg_png(layout)
    assert png is not None
    assert png.startswith(_PNG_MAGIC)


def test_truncation_above_50_nodes_no_crash():
    nodes = [
        {"id": f"n{i}", "type": "person", "label": f"L{i}",
         "trust_score": i / 70.0,
         "source_event_ids": [], "properties": {}}
        for i in range(70)
    ]
    png = render_kg_png({"nodes": nodes, "edges": []})
    assert png is not None
    assert png.startswith(_PNG_MAGIC)


def test_empty_layout_dict_no_crash():
    assert render_kg_png({}) is None or render_kg_png({}).startswith(_PNG_MAGIC)


def test_render_kg_png_b64_returns_valid_base64():
    layout = {
        "nodes": [{
            "id": "n", "type": "person", "label": "A", "trust_score": 0.9,
            "source_event_ids": [], "properties": {},
        }],
        "edges": [],
    }
    b64 = render_kg_png_b64(layout)
    assert b64 is not None
    # 应该能 decode 回 valid PNG
    raw = base64.b64decode(b64)
    assert raw.startswith(_PNG_MAGIC)


def test_render_kg_png_b64_empty_layout():
    """空 layout 也能 b64 化占位 PNG."""
    b64 = render_kg_png_b64({"nodes": [], "edges": []})
    assert b64 is not None
    raw = base64.b64decode(b64)
    assert raw.startswith(_PNG_MAGIC)


def test_edge_with_missing_endpoint_skipped():
    layout = {
        "nodes": [{
            "id": "n", "type": "person", "label": "A", "trust_score": 0.9,
            "source_event_ids": [], "properties": {},
        }],
        "edges": [{
            "id": "e", "source": "n", "target": "ghost", "type": "mentions",
            "weight": 1, "label": None, "source_event_ids": [],
        }],
    }
    png = render_kg_png(layout)
    assert png is not None
    # 不崩即可


def test_contradicts_edge_color_no_crash():
    """contradicts 用 danger 红色, 与默认颜色不同, 验证 dict lookup 正确."""
    layout = {
        "nodes": [
            {"id": "a", "type": "person", "label": "A", "trust_score": 0.9,
             "source_event_ids": [], "properties": {}},
            {"id": "b", "type": "event", "label": "B", "trust_score": 0.9,
             "source_event_ids": [], "properties": {}},
        ],
        "edges": [{
            "id": "ec", "source": "a", "target": "b", "type": "contradicts",
            "weight": 1, "label": None, "source_event_ids": [],
        }],
    }
    png = render_kg_png(layout)
    assert png is not None
    assert png.startswith(_PNG_MAGIC)
