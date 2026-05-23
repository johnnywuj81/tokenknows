"""v1.5 T100 · KG PNG 缩略图 (Pillow 纯 Python 绘制, 无系统依赖).

设计:
  - 与 thumbnail.py SVG 同布局算法 (4 列, 节点 circle, 边 line)
  - 输出 PNG bytes; chapter.layout.thumbnail_png_b64 存 base64
  - cairosvg 路径 (系统 cairo + svg → png) 留 v1.6 production 用; 当前 MVP 用 Pillow
  - 失败 silent (返回 None), assess stage 仅 log warning

注: Pillow 没有 antialiasing 高级特性, 视觉略糙; 但作为 list 卡片缩略图
( <=100px ) 完全够用. 真高分辨率截图等 v1.6 Playwright.
"""

from __future__ import annotations

import base64
import io
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover — Pillow 未装时 silent skip
    _PIL_AVAILABLE = False

# 与 SVG 版相同的视觉常量, 保持一致
_TYPE_COLOR_RGB = {
    "person": (202, 138, 4),    # warning-dark
    "event": (37, 99, 235),     # info-dark
    "concept": (22, 163, 74),   # success-dark
    "artifact": (220, 38, 38),  # danger-dark
}
_EDGE_COLOR_RGB = {
    "contradicts": (220, 38, 38),
    "caused_by": (202, 138, 4),
}
_EDGE_COLOR_DEFAULT_RGB = (148, 163, 184)
_BG_RGB = (250, 250, 249)
_CANVAS_W = 320
_CANVAS_H = 180
_NODE_R = 5
_MAX_NODES = 50


def render_kg_png(layout: dict[str, Any]) -> bytes | None:
    """生成 PNG bytes; 失败 (Pillow 不可用/数据异常) 返回 None.

    输入: KnowledgeGraphLayout dict (nodes/edges 必须).
    输出: PNG 字节. 调用方负责 base64 编码.
    """
    if not _PIL_AVAILABLE:
        return None

    nodes = layout.get("nodes") or []
    if not nodes:
        return _empty_png()

    sorted_nodes = sorted(
        nodes, key=lambda n: n.get("trust_score", 0.0), reverse=True,
    )[:_MAX_NODES]

    by_type: dict[str, list[dict]] = {
        "person": [], "event": [], "concept": [], "artifact": [],
    }
    for n in sorted_nodes:
        t = n.get("type")
        if t in by_type:
            by_type[t].append(n)

    positions: dict[str, tuple[float, float]] = {}
    col_w = _CANVAS_W / 4
    for col_idx, t in enumerate(["person", "event", "concept", "artifact"]):
        nodes_in_col = by_type[t]
        if not nodes_in_col:
            continue
        x = col_w * col_idx + col_w / 2
        gap = (_CANVAS_H - 24) / max(len(nodes_in_col), 1)
        for i, n in enumerate(nodes_in_col):
            y = 16 + gap * (i + 0.5)
            positions[n["id"]] = (x, y)

    try:
        img = Image.new("RGB", (_CANVAS_W, _CANVAS_H), _BG_RGB)
        draw = ImageDraw.Draw(img)

        # 边 (先画背景层)
        for e in layout.get("edges") or []:
            src = positions.get(e.get("source"))
            tgt = positions.get(e.get("target"))
            if not src or not tgt:
                continue
            color = _EDGE_COLOR_RGB.get(e.get("type"), _EDGE_COLOR_DEFAULT_RGB)
            draw.line([src, tgt], fill=color, width=1)

        # 节点
        for n in sorted_nodes:
            if n["id"] not in positions:
                continue
            x, y = positions[n["id"]]
            color = _TYPE_COLOR_RGB.get(n.get("type"), _EDGE_COLOR_DEFAULT_RGB)
            draw.ellipse(
                [x - _NODE_R, y - _NODE_R, x + _NODE_R, y + _NODE_R],
                fill=color, outline=color,
            )

        # 截断角标
        if len(nodes) > _MAX_NODES:
            omit = len(nodes) - _MAX_NODES
            try:
                font = ImageFont.load_default()
                draw.text(
                    (_CANVAS_W - 60, _CANVAS_H - 14),
                    f"+{omit} nodes",
                    fill=(107, 114, 128), font=font,
                )
            except Exception:  # noqa: BLE001 - font fallback
                pass

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:  # noqa: BLE001 - 渲染整体失败 silent skip
        return None


def render_kg_png_b64(layout: dict[str, Any]) -> str | None:
    """便利函数: PNG bytes → base64 string (供 layout.thumbnail_png_b64 存储).

    返回纯 base64 (不带 data: 前缀); 前端拼 `data:image/png;base64,{b64}` 用.
    """
    png = render_kg_png(layout)
    if png is None:
        return None
    return base64.b64encode(png).decode("ascii")


def _empty_png() -> bytes | None:
    """空 layout 占位 PNG."""
    if not _PIL_AVAILABLE:
        return None
    try:
        img = Image.new("RGB", (_CANVAS_W, _CANVAS_H), _BG_RGB)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return None
