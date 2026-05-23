"""Knowledge Graph schemas · v1.2.0 T81.

新 asset_type='knowledge_graph' 的载体: 单 Chapter 的 layout 字段塞整图 JSON.

设计依据:
- Proposal v1.2 (Plan rustling-pondering-sifakis)
- 参考 https://github.com/Lum1104/Understand-Anything (MIT) Agent prompt 思路;
  不复制 TS 代码 (后端是 Python).

节点类型 (4 种):
- person: 来自 ValueSegment.contributors / Event.author (im_user_id 锚定)
- event: PR / commit / incident / 群里高价值消息
- concept: 主题词 / 决策 (e.g. "JWT 迁移")
- artifact: 文件 / 文档 / PR / Skill

边类型 (6 种):
- authored_by (event → person)
- mentions (event → concept)
- depends_on (有向, event/concept 互连)
- contradicts (双向 - 决策冲突, assess 阶段自动补对称边)
- caused_by (incident 因果)
- related_to (兜底)

数据流:
    outline stage  → 抽节点骨架 (label + type + source_event_ids)
    content stage  → 抽边 + node.summary
    evidence stage → 验 source_event_ids 全部存在 + 反向写 EvidenceLink
    assess stage   → MinHash dedup + 双向化 + 孤立节点告警
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

KGNodeType = Literal["person", "event", "concept", "artifact"]

KGEdgeType = Literal[
    "authored_by",
    "mentions",
    "depends_on",
    "contradicts",
    "caused_by",
    "related_to",
]


class KGSpanAnchor(BaseModel):
    """节点在 chapter.content 中的 char_offset 锚点;
    供 EvidenceDrawer 跳转复用 (v1.2 不动 EvidenceDrawer)."""

    char_offset: int = Field(ge=0)
    """chapter.content 中 `<!-- node:<id> -->` 行的起始 char 位置."""


class KGNode(BaseModel):
    """单个图谱节点."""

    id: str = Field(..., min_length=1, max_length=64)
    """全局 short hash, 例如 'n_pr127' / 'n_alice'; LLM 生成时用语义前缀,
    持久化时统一; assess 阶段 dedup."""

    type: KGNodeType

    label: str = Field(..., min_length=1, max_length=120)
    """节点显示名 (UI 上节点正文)."""

    summary: str | None = Field(default=None, max_length=400)
    """≤ 120 字简介 (content stage 填), hover tooltip 用."""

    properties: dict[str, Any] = Field(default_factory=dict)
    """type-specific 元数据: person={im_user_id?}, event={occurred_at?, url?},
    artifact={path?, url?}, concept={tags?}."""

    source_event_ids: list[str] = Field(default_factory=list)
    """支撑该节点的 Event id 列表 (复用 Evidence 体系)."""

    trust_score: float = Field(default=0.5, ge=0.0, le=1.0)
    """抽取置信度 (LLM 自评或 source events 平均 trust)."""

    span_anchor: KGSpanAnchor | None = None
    """chapter.content 锚点 (evidence stage 后填)."""


class KGEdge(BaseModel):
    """单条有向边 (contradicts assess 后自动补反向)."""

    id: str = Field(..., min_length=1, max_length=64)
    source: str = Field(..., min_length=1, max_length=64)
    """source node id."""
    target: str = Field(..., min_length=1, max_length=64)
    """target node id."""

    type: KGEdgeType

    label: str | None = Field(default=None, max_length=200)
    """边的可读说明, e.g. 'PR #127 由 @alice 合并'."""

    weight: int = Field(default=1, ge=1, le=5)
    """1-5, UI 上反映为线粗细 (e.g. 多 evidence 支持 → weight=4)."""

    source_event_ids: list[str] = Field(default_factory=list)


class KGLayoutHints(BaseModel):
    """前端布局建议 (dagre 参数)."""

    algorithm: Literal["dagre", "force", "manual"] = "dagre"
    rankdir: Literal["LR", "TB", "BT", "RL"] = "LR"
    """LR = 左→右 (默认); TB = 上→下."""


class KnowledgeGraphLayout(BaseModel):
    """整图 JSON; 塞 chapter.layout.

    schema_version 用于将来 chapter.layout 兼容性 (v1.3 加全局 entity_registry
    时, 新版本字段不破坏老数据 round-trip).
    """

    schema_version: Literal["kg.v1"] = "kg.v1"
    nodes: list[KGNode] = Field(default_factory=list)
    edges: list[KGEdge] = Field(default_factory=list)
    layout_hints: KGLayoutHints = Field(default_factory=KGLayoutHints)

    # 解析失败兜底字段 (LLM 返无效 JSON 时存原始输出)
    parse_error: str | None = None
    raw_output: str | None = Field(default=None, max_length=4000)


# ─── LLM 阶段输出 DTO (用于严格解析) ──────────────────────────────


class KGOutlineLLMOutput(BaseModel):
    """outline stage LLM JSON 输出 schema.

    LLM 仅产节点骨架, edges 留 content stage 填.
    """

    nodes: list[KGNode] = Field(default_factory=list)


class KGNodeSummary(BaseModel):
    """content stage 补的节点 summary."""

    node_id: str
    summary: str = Field(..., max_length=400)


class KGContentLLMOutput(BaseModel):
    """content stage LLM JSON 输出 schema."""

    edges: list[KGEdge] = Field(default_factory=list)
    node_summaries: list[KGNodeSummary] = Field(default_factory=list)


__all__ = [
    "KGContentLLMOutput",
    "KGEdge",
    "KGEdgeType",
    "KGLayoutHints",
    "KGNode",
    "KGNodeSummary",
    "KGNodeType",
    "KGOutlineLLMOutput",
    "KGSpanAnchor",
    "KnowledgeGraphLayout",
]
