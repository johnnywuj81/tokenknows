"""Skill Marketplace · v1.0.0 T68-T69.

publish_public: 把 owner 项目内 active+approved skill 转 visibility=public,
让其他 project 在 marketplace 看见.

import_skill: 从 marketplace 复制 1 个 public skill 到自己 project, 留追溯
(source_skill_id / source_project_id).

设计原则:
- 不强依赖 owner 校验 (endpoint 层做); service 是纯函数
- import 默认 status=draft + review_state=not_submitted (走 v0.6 流程审批)
- import 不复制 metrics (新项目的 trust_score 重新累积)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.config.logging import logger
from app.schemas.skill import Skill


class MarketplaceError(Exception):
    """publish / import 操作非法."""


def publish_public(
    skill: Skill, *, now: datetime | None = None
) -> Skill:
    """把 skill 标记为 public + 设 published_at.

    前置:
    - status=active (deprecated / draft 不能 publish)
    - review_state=approved (没 Reviewer 把关的不能放市场)
    - 非 locked (locked 通常是固化历史版本)
    """
    if skill.status != "active":
        raise MarketplaceError(
            f"only active skill can be published, got status={skill.status}"
        )
    if skill.review_state != "approved":
        raise MarketplaceError(
            f"only reviewer-approved skill can be published, "
            f"got review_state={skill.review_state}"
        )
    if skill.locked:
        raise MarketplaceError("locked skill cannot be published")
    if skill.visibility == "public":
        return skill  # 幂等
    now_utc = now or datetime.now(timezone.utc)
    return skill.model_copy(update={
        "visibility": "public",
        "published_at": now_utc,
        "updated_at": now_utc,
    })


def unpublish(skill: Skill, *, now: datetime | None = None) -> Skill:
    """收回 public (visibility → private).

    幂等; 不动 status / review_state. 已经被其他 project import 的副本不受影响
    (他们各自独立的 skill).
    """
    if skill.visibility == "private":
        return skill
    now_utc = now or datetime.now(timezone.utc)
    return skill.model_copy(update={
        "visibility": "private",
        "published_at": None,
        "updated_at": now_utc,
    })


def list_marketplace(
    *,
    q: str | None = None,
    min_trust: float = 0.0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """跨所有 project 搜 public skill, 按 published_at DESC.

    Args:
        q: 名字 / skill_md preview 模糊匹配 (大小写不敏感; 简单 substr)
        min_trust: 过滤 trust_score < min_trust
        limit: 上限

    Returns: list of MarketplaceSkillCard dict.
    """
    from app.services import skill_service

    items: list[dict[str, Any]] = []
    try:
        q_lower = q.lower() if q else None
        for skill in skill_service.get_registry()._skills.values():  # noqa: SLF001
            if skill.visibility != "public":
                continue
            if skill.metrics.trust_score < min_trust:
                continue
            if q_lower:
                hay = (
                    skill.name.lower() + " " + skill.skill_md[:1000].lower()
                )
                if q_lower not in hay:
                    continue
            items.append({
                "skill_id": skill.id,
                "name": skill.name,
                "version": skill.version,
                "project_id": skill.project_id,
                "trust_score": skill.metrics.trust_score,
                "usage_count": skill.metrics.usage_count,
                "acceptance_count": skill.metrics.acceptance_count,
                "published_at": skill.published_at,
                "skill_md_preview": skill.skill_md[:500],
            })
        items.sort(
            key=lambda it: it["published_at"] or datetime.min, reverse=True
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("marketplace_list_failed", error=str(e))
    return items[:limit]


def import_skill(
    *,
    source_skill: Skill,
    target_project_id: str,
    name_hint: str | None = None,
    now: datetime | None = None,
) -> Skill:
    """从 source_skill (public) 复制到 target_project_id.

    新 skill:
    - id 新生成
    - project_id = target_project_id
    - status=draft, review_state=not_submitted (走本 project 的 Reviewer 流)
    - metrics 全部清零 (重新累积)
    - visibility=private (新副本默认不公开)
    - source_skill_id / source_project_id 留痕 (审计 + UI 显示)
    - parent_skill_id=None (不与原 evolve_chain 关联; 跨 project 不延续)

    Raises:
        MarketplaceError: source 非 public
    """
    if source_skill.visibility != "public":
        raise MarketplaceError(
            f"source skill {source_skill.id} is not public"
        )
    now_utc = now or datetime.now(timezone.utc)
    new_id = f"skill-{uuid.uuid4().hex[:12]}"
    new_skill = source_skill.model_copy(update={
        "id": new_id,
        "project_id": target_project_id,
        "name": name_hint or source_skill.name,
        "version": 1,  # 重新计版本
        "status": "draft",
        "review_state": "not_submitted",
        "review_history": [],
        "last_reviewer_id": None,
        "last_reviewed_at": None,
        "metrics": source_skill.metrics.model_copy(update={
            "usage_count": 0,
            "acceptance_count": 0,
            "rejection_count": 0,
            "avg_acceptance_rate": 0.0,
            "trust_score": 0.5,  # 新 import 给 0.5 起步
        }),
        "last_used_at": None,
        "visibility": "private",
        "published_at": None,
        "source_skill_id": source_skill.id,
        "source_project_id": source_skill.project_id,
        "imported_at": now_utc,
        "parent_skill_id": None,  # 跨 project 不延续 evolve_chain
        "distilled_from": [],  # 来源是 import, 不是新蒸馏
        "distilled_at": now_utc,
        # consent 字段重置 (import 后没有 contributor consent 需求)
        "contributors": [],
        "consent_required_from": [],
        "consent_signed_by": [],
        "consent_rejected_by": None,
        "consent_expires_at": None,
        "created_at": now_utc,
        "updated_at": now_utc,
        "locked": False,
        "embedding": None,  # import 后重新算 (避免脏 embedding)
    })
    return new_skill


__all__ = [
    "MarketplaceError",
    "import_skill",
    "list_marketplace",
    "publish_public",
    "unpublish",
]
