"""knowledge_graph.thumbnail · v1.3.1 T95 · KG 缩略图渲染.

MVP 实现: 纯 Python SVG 生成 (无 headless browser 依赖).

设计:
  - 输入: KnowledgeGraphLayout dict (nodes + edges + 可选 user_positions)
  - 输出: SVG string (内嵌, base64 不必要)
  - 算法: 简化 dagre-like LR layout (按 type 分列, 同 type 垂直排)
  - 大图 > 50 节点: 截断显示 top-N 按 trust_score, 余则省略
  - 配色: 与前端 Tailwind token 对齐 (warning/info/success/danger 四象限)

注: Playwright 真截图迁移在 v1.4+; 替换 render_kg_svg 实现即可, 调用方
不动. SVG 也支持作为 base64 内嵌 <img> 或 data: URI.
"""

from __future__ import annotations

import html
from typing import Any

# 视觉常量 — 与前端 Node 组件 (PersonNode 等) 颜色对齐
_TYPE_COLOR = {
    "person": "#ca8a04",   # warning-dark (黄)
    "event": "#2563eb",    # info-dark (蓝)
    "concept": "#16a34a",  # success-dark (绿)
    "artifact": "#dc2626", # danger-dark (红)
}

_EDGE_COLOR = {
    "contradicts": "#dc2626",
    "caused_by": "#ca8a04",
}
_EDGE_COLOR_DEFAULT = "#94a3b8"

_CANVAS_W = 320
_CANVAS_H = 180
_NODE_R = 5
_MAX_NODES = 50


def render_kg_svg(layout: dict[str, Any]) -> str:
    """根据 KG layout dict 生成 SVG thumbnail string.

    输入:
        layout: KnowledgeGraphLayout dict 形式 (nodes/edges 必须, 其余可选).
    返回:
        SVG XML 字符串, 形如 `<svg ...>...</svg>`.
        layout 为空 / 缺 nodes → 返回 占位 "空图" SVG.
    """
    nodes = layout.get("nodes") or []
    edges = layout.get("edges") or []

    if not nodes:
        return _empty_svg()

    # 截断 top-N
    sorted_nodes = sorted(
        nodes,
        key=lambda n: n.get("trust_score", 0.0),
        reverse=True,
    )[:_MAX_NODES]
    keep_ids = {n["id"] for n in sorted_nodes}

    # 按 type 分列
    by_type: dict[str, list[dict]] = {
        "person": [], "event": [], "concept": [], "artifact": [],
    }
    for n in sorted_nodes:
        t = n.get("type")
        if t in by_type:
            by_type[t].append(n)

    # 4 列布局, 每列 width = CANVAS_W / 4
    col_w = _CANVAS_W / 4
    positions: dict[str, tuple[float, float]] = {}
    for col_idx, t in enumerate(["person", "event", "concept", "artifact"]):
        nodes_in_col = by_type[t]
        if not nodes_in_col:
            continue
        x = col_w * col_idx + col_w / 2
        gap = (_CANVAS_H - 24) / max(len(nodes_in_col), 1)
        for i, n in enumerate(nodes_in_col):
            y = 16 + gap * (i + 0.5)
            positions[n["id"]] = (x, y)

    # SVG 元素
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {_CANVAS_W} {_CANVAS_H}" '
        f'preserveAspectRatio="xMidYMid meet" '
        f'role="img" aria-label="Knowledge graph thumbnail">',
        f'<rect width="{_CANVAS_W}" height="{_CANVAS_H}" '
        f'fill="#fafaf9"/>',  # bg-warm
    ]

    # 边 (背景层先画)
    for e in edges:
        src = positions.get(e.get("source"))
        tgt = positions.get(e.get("target"))
        if not src or not tgt:
            continue  # 端点已被截断
        color = _EDGE_COLOR.get(e.get("type"), _EDGE_COLOR_DEFAULT)
        parts.append(
            f'<line x1="{src[0]:.1f}" y1="{src[1]:.1f}" '
            f'x2="{tgt[0]:.1f}" y2="{tgt[1]:.1f}" '
            f'stroke="{color}" stroke-width="0.5" opacity="0.6"/>'
        )

    # 节点 (前景层)
    for n in sorted_nodes:
        if n["id"] not in positions:
            continue
        x, y = positions[n["id"]]
        color = _TYPE_COLOR.get(n.get("type"), "#94a3b8")
        label = html.escape((n.get("label") or "")[:24])
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{_NODE_R}" '
            f'fill="{color}" opacity="0.85"/>'
        )
        # 仅给前 8 个加 label, 其余太挤
        if sorted_nodes.index(n) < 8 and label:
            parts.append(
                f'<text x="{x:.1f}" y="{y - _NODE_R - 2:.1f}" '
                f'font-size="6" font-family="sans-serif" '
                f'fill="#374151" text-anchor="middle">{label}</text>'
            )

    # 截断告警角标 (>50 节点)
    if len(nodes) > _MAX_NODES:
        omit = len(nodes) - _MAX_NODES
        parts.append(
            f'<text x="{_CANVAS_W - 4}" y="{_CANVAS_H - 4}" '
            f'font-size="7" font-family="sans-serif" fill="#6b7280" '
            f'text-anchor="end">+{omit} nodes</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _empty_svg() -> str:
    """空 layout / 生成失败时的占位."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {_CANVAS_W} {_CANVAS_H}" role="img" '
        f'aria-label="Empty graph">'
        f'<rect width="{_CANVAS_W}" height="{_CANVAS_H}" fill="#fafaf9"/>'
        f'<text x="{_CANVAS_W / 2}" y="{_CANVAS_H / 2}" font-size="10" '
        f'font-family="sans-serif" fill="#94a3b8" text-anchor="middle">'
        f'(empty graph)</text></svg>'
    )
