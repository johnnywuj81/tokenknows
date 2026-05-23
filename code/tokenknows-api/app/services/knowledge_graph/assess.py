"""Knowledge Graph assess stage · v1.2.0 T82.

3 个 纯函数, 无 LLM / DB 依赖:
- dedup_nodes: 同义实体合并 (person 用 im_user_id 强匹配; 其他 type 用 normalized label)
- bidirect_contradicts: contradicts 边自动补反向
- find_isolated_nodes: 找零入度+零出度节点 (告警, 不删)

合并策略 (dedup):
- 同 type + 同 normalized label → 合并; keep 第一个 id, append source_event_ids
- person 额外: im_user_id 相同 → 一定合并 (即便 label 不同)
- 合并时: source_event_ids dedup-list-merge; trust_score 取 max; properties shallow merge
- 边的 source/target 引用被合并的 id → 重定向到 keep 的 id; (source, target, type) dedup
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from app.schemas.knowledge_graph import KGEdge, KGNode


def _normalize_label(label: str) -> str:
    """Unicode 归一化 + 去标点 + lowercase, 用于 MinHash 兜底匹配.

    e.g. 'PR #127' / 'PR#127' / 'pr-127' → 'pr127'
    """
    # NFKC 归一: 全角 / 半角 统一
    s = unicodedata.normalize("NFKC", label.strip())
    # 移除标点 + 空白
    s = re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE)
    return s.lower()


def _merge_nodes(keep: KGNode, drop: KGNode) -> KGNode:
    """合并 drop 到 keep; source_event_ids + properties + trust_score."""
    merged_events = list(dict.fromkeys(keep.source_event_ids + drop.source_event_ids))
    merged_props = {**drop.properties, **keep.properties}  # keep 优先
    return keep.model_copy(update={
        "source_event_ids": merged_events,
        "properties": merged_props,
        "trust_score": max(keep.trust_score, drop.trust_score),
        # summary: keep 优先非空; 否则用 drop
        "summary": keep.summary or drop.summary,
    })


def dedup_nodes(
    nodes: list[KGNode],
    edges: list[KGEdge],
) -> tuple[list[KGNode], list[KGEdge], int]:
    """同义实体合并; 返回 (新 nodes, 重定向后 edges, 合并掉的节点数).

    优先级:
    1. person + 同 im_user_id → 合并 (即便 label 不同)
    2. 同 type + 同 normalized label → 合并
    """
    if not nodes:
        return [], edges, 0

    # 建索引
    keep_by_key: dict[tuple[str, str], KGNode] = {}  # (type, key) → keep node
    id_remap: dict[str, str] = {}  # old_id → keep_id
    out_nodes: list[KGNode] = []
    merged_count = 0

    for node in nodes:
        # person 优先 im_user_id 匹配
        if node.type == "person":
            im_uid = node.properties.get("im_user_id")
            if im_uid:
                key = ("person", f"im:{im_uid}")
            else:
                key = ("person", _normalize_label(node.label))
        else:
            key = (node.type, _normalize_label(node.label))

        if key in keep_by_key:
            existing = keep_by_key[key]
            merged = _merge_nodes(existing, node)
            keep_by_key[key] = merged
            id_remap[node.id] = existing.id
            merged_count += 1
            # 替换 out_nodes 中对应的 keep 节点
            for i, n in enumerate(out_nodes):
                if n.id == existing.id:
                    out_nodes[i] = merged
                    break
        else:
            keep_by_key[key] = node
            id_remap[node.id] = node.id
            out_nodes.append(node)

    # 重定向 edges; 去重 (source, target, type) 同三元组
    out_edges: list[KGEdge] = []
    seen_edge_keys: set[tuple[str, str, str]] = set()
    for edge in edges:
        new_source = id_remap.get(edge.source, edge.source)
        new_target = id_remap.get(edge.target, edge.target)
        # 自环 (合并后 source == target) 丢弃
        if new_source == new_target:
            continue
        edge_key = (new_source, new_target, edge.type)
        if edge_key in seen_edge_keys:
            continue
        seen_edge_keys.add(edge_key)
        out_edges.append(edge.model_copy(update={
            "source": new_source,
            "target": new_target,
        }))

    return out_nodes, out_edges, merged_count


def bidirect_contradicts(edges: list[KGEdge]) -> list[KGEdge]:
    """contradicts 边自动补反向边 (保证图谱视觉对称).

    新边 id = "rev_<orig_id>"; type 仍是 contradicts; source/target 交换.
    若反向边已存在则不重复添加.
    """
    existing_keys: set[tuple[str, str, str]] = set()
    for e in edges:
        existing_keys.add((e.source, e.target, e.type))

    new_edges: list[KGEdge] = list(edges)
    for e in edges:
        if e.type != "contradicts":
            continue
        rev_key = (e.target, e.source, "contradicts")
        if rev_key in existing_keys:
            continue
        new_edges.append(e.model_copy(update={
            "id": f"rev_{e.id}",
            "source": e.target,
            "target": e.source,
        }))
        existing_keys.add(rev_key)
    return new_edges


def find_isolated_nodes(
    nodes: list[KGNode], edges: list[KGEdge]
) -> list[str]:
    """找零入度 + 零出度的节点 id (告警用; 不删)."""
    referenced: set[str] = set()
    for e in edges:
        referenced.add(e.source)
        referenced.add(e.target)
    return [n.id for n in nodes if n.id not in referenced]


def compute_assess_metrics(
    nodes: list[KGNode],
    edges: list[KGEdge],
    isolated_ids: list[str],
    merged_count: int,
) -> dict:
    """AssetMetrics 兼容输出. 复用 coverage/citation_density/slop_score 语义.

    - coverage: 有 source_event_ids 的节点占比
    - citation_density: 每节点平均 source_event_ids 数 (max 5, 截断为 0-1 比例)
    - slop_score: 合并率 (重复实体多→ slop 高); merged_count / orig_total
    - similarity: None (图谱无连贯度概念)
    - consistency_score: 1 - 孤立节点率
    """
    if not nodes:
        return {
            "coverage": 0.0,
            "citation_density": 0.0,
            "slop_score": 0.0,
            "similarity": 0.0,
            "consistency_score": None,
        }

    total = len(nodes)
    with_events = sum(1 for n in nodes if n.source_event_ids)
    coverage = with_events / total

    avg_events = sum(len(n.source_event_ids) for n in nodes) / total
    # 5 个 event 视为饱和, 截断到 [0, 1]
    citation_density = min(1.0, avg_events / 5.0)

    # slop = 重复实体合并率
    orig_total = total + merged_count
    slop_score = (merged_count / orig_total) if orig_total > 0 else 0.0

    isolated_rate = len(isolated_ids) / total
    consistency = max(0.0, 1.0 - isolated_rate)

    return {
        "coverage": round(coverage, 4),
        "citation_density": round(citation_density, 4),
        "slop_score": round(slop_score, 4),
        "similarity": 0.0,  # 图谱无相似度概念, 设 0 (而非 None) 让 AssetMetrics 校验通过
        "consistency_score": round(consistency, 4),
    }


__all__ = [
    "bidirect_contradicts",
    "compute_assess_metrics",
    "dedup_nodes",
    "find_isolated_nodes",
]
