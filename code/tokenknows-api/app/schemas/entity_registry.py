"""v1.3.1 T96 · ProjectEntityRegistry — 跨 KG asset 的实体合并.

设计:
  - project 维度去重 (不跨 project — Skill marketplace 那边才跨, 这里语义不同)
  - canonical_label = label.strip().lower() + 类型 (person 'alice' / 'Alice' 同一)
  - source_node_refs 记每个 asset/chapter/node 三元组, 便于反查
  - aliases 收集变体 label (用户可在前端看到"也叫 X")
  - MVP 不跨 project; v1.4+ 加 global registry + 项目间映射
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field

KGNodeType = Literal["person", "event", "concept", "artifact"]


class EntitySourceRef(BaseModel):
    """一条实体在某 asset/chapter/node 的引用记录."""

    asset_id: str
    chapter_id: str
    node_id: str
    """KG 节点 id (chapter.layout.nodes 里的 id)."""


class ProjectEntity(BaseModel):
    """v1.3.1 T96 · project 内规范化的实体记录."""

    id: str
    project_id: str
    type: KGNodeType
    canonical_label: str
    """label.strip().lower() 用于 dedup; UI 显示原始 label."""
    label: str
    """首次见到的原始 label (UI 显示用)."""
    aliases: list[str] = Field(default_factory=list)
    """除 label 外见过的所有变体 (去重)."""
    source_refs: list[EntitySourceRef] = Field(default_factory=list)
    first_seen_at: datetime
    last_seen_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def asset_count(self) -> int:
        """该实体出现在多少个不同 asset 里. Pydantic computed → JSON 序列化."""
        return len({r.asset_id for r in self.source_refs})


class EntitySourceItem(BaseModel):
    """GET /entities/:id/sources 单条返回 (asset 维度合并)."""

    asset_id: str
    asset_title: str
    asset_type: str
    chapter_ids: list[str]
    node_ids: list[str]


# ── v1.5 T99 · global (cross-project) entity ──────────────────────


class GlobalEntityLink(BaseModel):
    """global entity 关联的某个 project entity (反查用)."""

    project_id: str
    project_entity_id: str


class GlobalEntity(BaseModel):
    """v1.5 T99 · 跨 project 的全局实体 (类似 Skill marketplace).

    project entity 通过 publish_to_global 显式发布到 global; 不自动同步.
    """

    id: str
    type: KGNodeType
    canonical_label: str
    label: str
    aliases: list[str] = Field(default_factory=list)
    linked: list[GlobalEntityLink] = Field(default_factory=list)
    """所有关联到此 global 的 (project_id, project_entity_id) 对."""
    created_by: str | None = None
    """首次 publish 的 user_id (审计用)."""
    created_at: datetime
    last_seen_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def project_count(self) -> int:
        """该 global entity 跨多少 project."""
        return len({link.project_id for link in self.linked})


# ── v1.6 T102 · audit log ─────────────────────────────────────────


class EntityAuditLog(BaseModel):
    """v1.6 T102 · entity merge/split 操作审计日志.

    payload 内容随 op_type 不同:
      - merge: {source_snapshot (ProjectEntity dict), target_id, target_label}
      - split: {source_id, new_entity_id, moved_node_ref: {asset_id, chapter_id, node_id}, new_canonical}
    """

    id: str
    project_id: str
    op_type: Literal["merge", "split"]
    actor_id: str | None = None
    created_at: datetime
    payload: dict
    undone: bool = False
    undone_at: datetime | None = None
    undone_by: str | None = None
