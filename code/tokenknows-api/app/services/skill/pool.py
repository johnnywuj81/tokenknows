"""Skill 池治理 · v0.7.0 T59-T61.

跨多模块共享的 helper: 找 failing chapters, 扫候选 evolve / deprecate.
"""

from __future__ import annotations

from typing import Any

from app.config.logging import logger


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


__all__ = [
    "collect_evolve_candidates",
    "collect_failing_chapters_for_skill",
]
