"""Skill 池治理 · v0.7.0 T59-T61.

跨多模块共享的 helper: 找 failing chapters, 扫候选 evolve / deprecate / trust recompute.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.config.logging import logger


# T60 deprecation 阈值
DORMANT_DAYS = 60
"""last_used_at 超过此天数 → 候选 dormant deprecation."""

LOW_TRUST_FLOOR = 0.2
"""trust_score 低于此值 → 候选 low-trust deprecation."""


def collect_failing_chapters_for_skill(
    project_id: str, skill_id: str
) -> list[dict[str, Any]]:
    """找出: 本 project 下 chapter 应用过此 skill 且 approval_state=rejected.

    供 evolve_skill_v2 / skill_evolve_checker_job 使用.
    避开 HTTP 层的 _collect_failing_chapters; 这里是 service-level 入口.
    """
    # 延迟 import 避免循环 (generation_service ↔ skill_service)
    from app.services import generation_service

    failing: list[dict] = []
    for asset_id, chapters in generation_service._chapters.items():
        asset = generation_service._assets.get(asset_id)
        if asset is None or asset.project_id != project_id:
            continue
        for ch in chapters:
            if ch.approval_state != "rejected":
                continue
            applied = getattr(ch, "applied_skills", None) or []
            if any(a.get("skill_id") == skill_id for a in applied):
                failing.append(ch.model_dump(mode="json"))
    return failing


def collect_evolve_candidates() -> list[dict[str, Any]]:
    """扫所有 skill, 返回 should_evolve=True 的候选.

    Returns: [{"skill_id", "project_id", "name", "version", "usage_count",
               "avg_acceptance_rate"}, ...]
    """
    from app.services import skill_service

    candidates: list[dict[str, Any]] = []
    try:
        # _registry._skills 是 dict[skill_id, Skill]; 内存全量遍历
        for skill in skill_service.get_registry()._skills.values():  # noqa: SLF001
            if skill_service.should_evolve(skill):
                candidates.append({
                    "skill_id": skill.id,
                    "project_id": skill.project_id,
                    "name": skill.name,
                    "version": skill.version,
                    "usage_count": skill.metrics.usage_count,
                    "avg_acceptance_rate": skill.metrics.avg_acceptance_rate,
                })
    except Exception as e:  # noqa: BLE001
        logger.warning("collect_evolve_candidates_failed", error=str(e))
    return candidates


def recompute_all_trust_scores(*, now: datetime | None = None) -> dict[str, int]:
    """T61: 每日重算所有 active/draft skill 的 trust_score.

    问题: _compute_trust_score 的 recency_decay = exp(-days/30) 是时间函数,
    但当前只在 on_chapter_state_changed 时算; 不用的 skill recency_decay
    自然衰减但 trust_score 不更新 → select_skills 排序失真.

    解法: 每天 02:00 全量 recompute. 不动 metrics 计数 (acceptance/rejection/
    usage), 只重算 trust_score.

    Returns:
        {"scanned": N, "updated": M, "skipped": K}
        updated = trust_score 真有变 (避免无谓 disk write);
        skipped = deprecated/locked 等不动的 status.
    """
    from app.services import skill_service
    from app.services.skill_service import _compute_trust_score

    scanned = 0
    updated = 0
    skipped = 0
    try:
        for skill_id, skill in list(
            skill_service.get_registry()._skills.items()  # noqa: SLF001
        ):
            scanned += 1
            if skill.status not in ("active", "draft"):
                skipped += 1
                continue
            if skill.locked:
                skipped += 1
                continue
            new_trust = _compute_trust_score(
                acceptance=skill.metrics.acceptance_count,
                rejection=skill.metrics.rejection_count,
                usage=skill.metrics.usage_count,
                last_used_at=skill.last_used_at,
            )
            # 浮点 noise tolerance: 差异 < 1e-4 不写
            if abs(new_trust - skill.metrics.trust_score) < 1e-4:
                continue
            new_metrics = skill.metrics.model_copy(
                update={"trust_score": new_trust}
            )
            new_skill = skill.model_copy(update={
                "metrics": new_metrics,
                "updated_at": now or datetime.now(timezone.utc),
            })
            skill_service.get_registry().update(new_skill)
            updated += 1
    except Exception as e:  # noqa: BLE001
        logger.warning("recompute_all_trust_scores_failed", error=str(e))
    return {"scanned": scanned, "updated": updated, "skipped": skipped}


def collect_deprecation_candidates(
    *, now: datetime | None = None
) -> list[dict[str, Any]]:
    """扫所有 active skill, 返回 dormant 或 low-trust 候选.

    规则:
    - active 状态 (deprecated/locked 不动)
    - 满足任一: last_used_at < now - 60d  或  trust_score < 0.2
    - 从未使用过 (last_used_at=None) 且超过 60 天 created 仍未用 → 也算 dormant

    Returns:
        [{"skill_id", "project_id", "name", "reason": "dormant|low_trust",
          "last_used_at", "trust_score", "contributors"}, ...]
    """
    from app.services import skill_service

    now_utc = now or datetime.now(timezone.utc)
    dormant_cutoff = now_utc - timedelta(days=DORMANT_DAYS)
    candidates: list[dict[str, Any]] = []
    try:
        for skill in skill_service.get_registry()._skills.values():  # noqa: SLF001
            if skill.status != "active":
                continue
            if skill.locked:
                continue
            reason: str | None = None
            # last_used_at None 时, 用 created_at 比较
            reference_time = skill.last_used_at or skill.created_at
            if reference_time < dormant_cutoff:
                reason = "dormant"
            elif skill.metrics.trust_score < LOW_TRUST_FLOOR:
                reason = "low_trust"
            if reason is None:
                continue
            candidates.append({
                "skill_id": skill.id,
                "project_id": skill.project_id,
                "name": skill.name,
                "reason": reason,
                "last_used_at": (
                    skill.last_used_at.isoformat()
                    if skill.last_used_at else None
                ),
                "trust_score": skill.metrics.trust_score,
                "contributors": list(skill.contributors),
                "last_reviewer_id": skill.last_reviewer_id,
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("collect_deprecation_candidates_failed", error=str(e))
    return candidates


__all__ = [
    "DORMANT_DAYS",
    "LOW_TRUST_FLOOR",
    "collect_deprecation_candidates",
    "collect_evolve_candidates",
    "collect_failing_chapters_for_skill",
    "recompute_all_trust_scores",
]
