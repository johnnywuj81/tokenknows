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
        for skill in skill_service.get_registry().all_skills():
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
        for skill_id, skill in skill_service.get_registry().all_skill_items():
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
        for skill in skill_service.get_registry().all_skills():
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


def build_governance_summary(
    project_id: str, *, now: datetime | None = None
) -> dict[str, Any]:
    """T62 · 项目级 Skill 池总览 (dashboard 用).

    v1.2 perf (T80): 合并 3 次全量扫描为 1 次, 复用 should_evolve /
    dormant / low_trust 判定. 每个 skill 仅 instance-level check 一次.

    返回 dict 而非 Pydantic (endpoint 层再 wrap), 便于复用.
    """
    from app.services import skill_service

    now_utc = now or datetime.now(timezone.utc)
    dormant_cutoff = now_utc - timedelta(days=DORMANT_DAYS)

    by_status: dict[str, int] = {}
    by_review_state: dict[str, int] = {}
    total = 0
    trust_sum = 0.0
    trust_count = 0
    evolve_n = 0
    dormant_n = 0
    low_trust_n = 0

    try:
        # 单次扫描, 用 list_skills 已按 project filter (无需再判断 project_id)
        skills = skill_service.list_skills(project_id)
        for s in skills:
            total += 1
            by_status[s.status] = by_status.get(s.status, 0) + 1
            by_review_state[s.review_state] = (
                by_review_state.get(s.review_state, 0) + 1
            )

            # active skill 累计 trust 平均
            if s.status == "active":
                trust_sum += s.metrics.trust_score
                trust_count += 1

                # active + non-locked → 检查 deprecation 候选
                if not s.locked:
                    ref_time = s.last_used_at or s.created_at
                    if ref_time < dormant_cutoff:
                        dormant_n += 1
                    elif s.metrics.trust_score < LOW_TRUST_FLOOR:
                        low_trust_n += 1

            # evolve 候选: 复用 should_evolve (usage>=20, acc<0.5, 非 locked)
            if skill_service.should_evolve(s):
                evolve_n += 1
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "governance_summary_failed",
            project_id=project_id, error=str(e),
        )

    avg_trust = trust_sum / trust_count if trust_count > 0 else 0.0

    return {
        "project_id": project_id,
        "total": total,
        "by_status": by_status,
        "by_review_state": by_review_state,
        "evolve_candidates": evolve_n,
        "dormant_candidates": dormant_n,
        "low_trust_candidates": low_trust_n,
        "avg_trust_score": round(avg_trust, 4),
    }


def build_evolve_chain(skill_id: str) -> list[dict[str, Any]]:
    """T62 · 构造 evolve 链 (parent 向上追溯 + children 向下扩展).

    返回按 version 升序的 list of dict 节点; is_current 标记被查询的 skill 自身.
    若 skill 不存在, 返 [].
    """
    from app.services import skill_service

    target = skill_service.get_skill(skill_id)
    if target is None:
        return []

    # parent 链: 向上追溯到没有 parent 的 root
    # v1.0.1 (review fix): seen 集合包含 target.id 防 cycle 回到自身
    parents: list[Any] = []
    seen_parent_ids: set[str] = {target.id}
    cur = target
    while cur.parent_skill_id:
        if cur.parent_skill_id in seen_parent_ids:
            break  # 防环 (包含回到 target / 直接重复)
        parent = skill_service.get_skill(cur.parent_skill_id)
        if parent is None:
            break
        parents.append(parent)
        seen_parent_ids.add(parent.id)
        cur = parent
    parents.reverse()

    # children 链: 找 parent_skill_id 链上指向 target 的 skill
    # 单进程内存全量遍历足够; 大量 skill 时建议建反向 index
    children: list[Any] = []
    seen = {target.id}
    queue = [target.id]
    while queue:
        current_id = queue.pop(0)
        for s in skill_service.get_registry()._skills.values():  # noqa: SLF001
            if s.parent_skill_id == current_id and s.id not in seen:
                children.append(s)
                seen.add(s.id)
                queue.append(s.id)
    children.sort(key=lambda s: s.version)

    chain = parents + [target] + children
    return [
        {
            "skill_id": s.id,
            "name": s.name,
            "version": s.version,
            "status": s.status,
            "parent_skill_id": s.parent_skill_id,
            "created_at": s.created_at,
            "is_current": s.id == skill_id,
        }
        for s in chain
    ]


__all__ = [
    "DORMANT_DAYS",
    "LOW_TRUST_FLOOR",
    "build_evolve_chain",
    "build_governance_summary",
    "collect_deprecation_candidates",
    "collect_evolve_candidates",
    "collect_failing_chapters_for_skill",
    "recompute_all_trust_scores",
]
