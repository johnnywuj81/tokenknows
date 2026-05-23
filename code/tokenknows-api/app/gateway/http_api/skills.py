"""HTTP API · v0.2 · Agent 专家技能 (Skills).

端点:
    GET    /projects/:id/skills?status=        列表 (按 trust_score DESC)
    GET    /skills/:id                         详情 (含 skill_md / metrics)
    POST   /projects/:id/skills/distill        从 chapter 蒸馏 (LLM)
    PATCH  /skills/:id                         编辑 skill_md / name / locked / status
    POST   /skills/:id/lock                    人工固化 (locked=True)
    POST   /skills/:id/unlock                  解锁
    POST   /skills/:id/evolve                  强制 v2 蒸馏 (low-acc skill)
    DELETE /skills/:id                         彻底删除

设计依据:
- PRD §5.8 Skill 自进化机制 (H1-H5)
- TDD §6 API 大全
- 计划 Milestone C HTTP endpoints
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config.logging import logger
from app.schemas.skill import (
    ConsentRejectRequest,
    ConsentRejectResponse,
    ConsentSignRequest,
    ConsentSignResponse,
    MarketplaceListResponse,
    MarketplaceSkillCard,
    Skill,
    SkillDistillRequest,
    SkillEvolveChainResponse,
    SkillGovernanceSummary,
    SkillImportRequest,
    SkillPublishResponse,
    SkillReviewActionResponse,
    SkillReviewApproveRequest,
    SkillReviewRejectRequest,
    SkillSubmitForReviewRequest,
    SkillUpdateRequest,
)
from app.gateway.http_api._session import get_current_user_id, require_user_id
from app.services import generation_service, skill_service
from app.services.project import membership
from app.services.skill import consent as skill_consent
from app.services.skill import marketplace as skill_marketplace
from app.services.skill import pool as skill_pool
from app.services.skill import review as skill_review

router = APIRouter()


@router.get("/projects/{project_id}/skills", response_model=list[Skill])
async def list_project_skills(
    project_id: str,
    status: str | None = None,
) -> list[Skill]:
    """列出项目 skills (按 trust_score DESC).

    Query:
        status: draft / active / deprecated 之一; 省略时返回全部
    """
    return skill_service.list_skills(project_id, status=status)  # type: ignore[arg-type]


@router.get("/skills/{skill_id}", response_model=Skill)
async def get_skill(skill_id: str) -> Skill:
    skill = skill_service.get_skill(skill_id)
    if skill is None:
        raise HTTPException(404, detail="Skill not found")
    return skill


@router.post(
    "/projects/{project_id}/skills/distill",
    response_model=Skill,
    status_code=201,
)
async def distill_skill_endpoint(
    project_id: str,
    body: SkillDistillRequest,
) -> Skill:
    """从指定 chapter list 蒸馏一份新 skill (status=draft).

    Body:
        source_chapter_ids: 1-10 个 chapter id
        name_hint: 可选名称提示
    """
    # 拉对应 chapter dumps (需 chapter belongs to one of project_id 的 asset)
    sources = _collect_source_chapters(project_id, body.source_chapter_ids)
    if not sources:
        raise HTTPException(
            404, detail="source_chapter_ids 找不到任何属于此项目的章节"
        )
    try:
        skill = await skill_service.distill_skill(
            project_id=project_id,
            source_chapters=sources,
            name_hint=body.name_hint,
            project_label=project_id,
        )
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    except Exception as e:
        logger.error("skill_distill_failed", project_id=project_id, error=str(e))
        raise HTTPException(500, detail=f"LLM 蒸馏失败: {e}") from e
    return skill


@router.patch("/skills/{skill_id}", response_model=Skill)
async def update_skill_endpoint(
    skill_id: str,
    body: SkillUpdateRequest,
) -> Skill:
    """部分更新 skill (skill_md / name / locked / status)."""
    updated = skill_service.update_skill(
        skill_id=skill_id,
        skill_md=body.skill_md,
        name=body.name,
        locked=body.locked,
        status=body.status,
    )
    if updated is None:
        raise HTTPException(404, detail="Skill not found")
    return updated


@router.post("/skills/{skill_id}/lock", response_model=Skill)
async def lock_skill(skill_id: str) -> Skill:
    """人工固化版本: 不再参与自进化."""
    updated = skill_service.update_skill(skill_id=skill_id, locked=True)
    if updated is None:
        raise HTTPException(404, detail="Skill not found")
    return updated


@router.post("/skills/{skill_id}/unlock", response_model=Skill)
async def unlock_skill(skill_id: str) -> Skill:
    updated = skill_service.update_skill(skill_id=skill_id, locked=False)
    if updated is None:
        raise HTTPException(404, detail="Skill not found")
    return updated


@router.post("/skills/{skill_id}/evolve", response_model=Skill)
async def evolve_skill_endpoint(skill_id: str) -> Skill:
    """强制触发 evolve_skill_v2 (用 fast-failing chapter 重新蒸馏).

    MVP 实现: 找到所有 chapter.applied_skills 含此 skill_id 且 approval_state=rejected
            的章节作为 failing_chapters.
    """
    skill = skill_service.get_skill(skill_id)
    if skill is None:
        raise HTTPException(404, detail="Skill not found")
    if skill.locked:
        raise HTTPException(409, detail="Skill 已锁定, 不能进化")
    failing = _collect_failing_chapters(skill.project_id, skill_id)
    if not failing:
        raise HTTPException(
            409,
            detail="没有可用的失败样本 (rejected chapter applied 此 skill)",
        )
    new_skill = await skill_service.evolve_skill_v2(
        skill_id=skill_id,
        failing_chapters=failing,
        project_label=skill.project_id,
    )
    if new_skill is None:
        raise HTTPException(500, detail="进化失败")
    return new_skill


@router.delete("/skills/{skill_id}", status_code=204)
async def delete_skill_endpoint(skill_id: str) -> None:
    if not skill_service.delete_skill(skill_id):
        raise HTTPException(404, detail="Skill not found")
    return None


# ─── v0.5.1 · Consent endpoints (T50) ──────────────────────────


@router.post(
    "/skills/{skill_id}/consent/sign",
    response_model=ConsentSignResponse,
)
async def sign_consent_endpoint(
    skill_id: str,
    body: ConsentSignRequest,
    session_user: str | None = Depends(get_current_user_id),
) -> ConsentSignResponse:
    """Contributor 签字同意发布该 skill.

    全员签 → status 自动转 draft (进入 Reviewer 审批流).
    幂等: 同一 user 第二次 sign 返 200 但只计一次.
    v1.0.1: 若传 X-User-Id, 校验 session_user == body.user_id (防伪造);
    backward-compat: 无 header 时退化用 body.user_id (老 IM 跳链接).
    """
    skill = skill_service.get_skill(skill_id)
    if skill is None:
        raise HTTPException(404, detail="Skill not found")
    if skill.status != "pending_contributor_consent":
        raise HTTPException(
            409,
            detail=(
                f"Skill status={skill.status}; "
                f"consent sign 仅在 pending_contributor_consent 阶段允许"
            ),
        )
    # v1.0.1 安全修复: session_user 必须与 body.user_id 一致 (有 session 时)
    if session_user and session_user != body.user_id:
        raise HTTPException(
            403,
            detail="body.user_id mismatch with X-User-Id session",
        )
    if body.user_id not in skill.consent_required_from:
        raise HTTPException(
            403,
            detail=(
                f"user_id {body.user_id} 不在 consent_required_from 列表; "
                f"required={skill.consent_required_from}"
            ),
        )
    try:
        new_skill, all_signed = skill_consent.sign_consent(
            skill,
            user_id=body.user_id,
            channel=body.channel,
            note=body.note,
        )
    except skill_consent.InvalidTransition as e:
        raise HTTPException(409, detail=str(e)) from e

    skill_service.get_registry().update(new_skill)
    # 回执通知给其他 contributor
    try:
        from app.services.im import consent_notifier
        other = [
            u for u in new_skill.consent_required_from if u != body.user_id
        ]
        if other:
            consent_notifier.notify_followup(
                new_skill,
                type_="consent_signed",
                recipient_user_ids=other,
                actor_user_id=body.user_id,
            )
    except Exception as e:
        logger.warning(
            "consent_sign_followup_failed", skill_id=skill_id, error=str(e)
        )

    return ConsentSignResponse(
        skill_id=new_skill.id,
        current_status=new_skill.status,
        signed_count=len(new_skill.consent_signed_by),
        required_count=len(new_skill.consent_required_from),
        all_signed=all_signed,
    )


@router.post(
    "/skills/{skill_id}/consent/reject",
    response_model=ConsentRejectResponse,
)
async def reject_consent_endpoint(
    skill_id: str,
    body: ConsentRejectRequest,
    session_user: str | None = Depends(get_current_user_id),
) -> ConsentRejectResponse:
    """Contributor 拒绝该 skill 发布 (单否决冻结).

    一旦任一 contributor 拒绝, status → rejected_by_contributor;
    其他人后续 sign 无效 (409).
    v1.0.1: session_user 必须与 body.user_id 一致 (有 session 时).
    """
    skill = skill_service.get_skill(skill_id)
    if skill is None:
        raise HTTPException(404, detail="Skill not found")
    if skill.status != "pending_contributor_consent":
        raise HTTPException(
            409,
            detail=(
                f"Skill status={skill.status}; "
                f"consent reject 仅在 pending_contributor_consent 阶段允许"
            ),
        )
    if session_user and session_user != body.user_id:
        raise HTTPException(
            403,
            detail="body.user_id mismatch with X-User-Id session",
        )
    if body.user_id not in skill.consent_required_from:
        raise HTTPException(
            403,
            detail=(
                f"user_id {body.user_id} 不在 consent_required_from 列表"
            ),
        )
    try:
        new_skill = skill_consent.reject_consent(
            skill,
            user_id=body.user_id,
            channel=body.channel,
            reason=body.reason,
        )
    except skill_consent.InvalidTransition as e:
        raise HTTPException(409, detail=str(e)) from e

    skill_service.get_registry().update(new_skill)
    try:
        from app.services.im import consent_notifier
        other = [
            u for u in new_skill.consent_required_from if u != body.user_id
        ]
        if other:
            consent_notifier.notify_followup(
                new_skill,
                type_="consent_rejected",
                recipient_user_ids=other,
                actor_user_id=body.user_id,
            )
    except Exception as e:
        logger.warning(
            "consent_reject_followup_failed", skill_id=skill_id, error=str(e)
        )

    return ConsentRejectResponse(
        skill_id=new_skill.id,
        current_status=new_skill.status,
        rejected_by=body.user_id,
    )


# ─── v0.6.0 · Reviewer 审批 endpoints (T57) ────────────────────


@router.get(
    "/projects/{project_id}/skills/pending-review",
    response_model=list[Skill],
)
async def list_pending_review_skills(project_id: str) -> list[Skill]:
    """Reviewer Inbox: 该项目下所有 review_state=pending_review 的 skill."""
    all_skills = skill_service.list_skills(project_id)
    return [s for s in all_skills if s.review_state == "pending_review"]


@router.post(
    "/skills/{skill_id}/submit-for-review",
    response_model=SkillReviewActionResponse,
)
async def submit_for_review_endpoint(
    skill_id: str,
    body: SkillSubmitForReviewRequest,
    session_user: str | None = Depends(get_current_user_id),
) -> SkillReviewActionResponse:
    """作者提交 skill 等待审批 (draft → review_state=pending_review).

    通知策略: 默认通知该 project 下所有 contributor 作为潜在 reviewer
    (生产应换为 project_owner / 显式 reviewer role).
    v1.0.1: session_user 必须与 body.user_id 一致 (有 session 时).
    """
    skill = skill_service.get_skill(skill_id)
    if skill is None:
        raise HTTPException(404, detail="Skill not found")
    if session_user and session_user != body.user_id:
        raise HTTPException(
            403,
            detail="body.user_id mismatch with X-User-Id session",
        )
    if skill.status != "draft":
        raise HTTPException(
            409,
            detail=(
                f"skill status={skill.status}; "
                f"submit-for-review 仅在 status=draft 阶段允许"
            ),
        )
    try:
        new_skill = skill_review.submit_for_review(
            skill, user_id=body.user_id, note=body.note
        )
    except skill_review.InvalidReviewTransition as e:
        raise HTTPException(409, detail=str(e)) from e

    skill_service.get_registry().update(new_skill)
    # 通知潜在 reviewer (contributors 列表)
    try:
        from app.services.skill import review_notifier
        reviewers = [
            uid for uid in new_skill.contributors if uid != body.user_id
        ]
        if reviewers:
            review_notifier.notify_review_request(
                new_skill,
                reviewer_user_ids=reviewers,
                author_user_id=body.user_id,
            )
    except Exception as e:
        logger.warning(
            "submit_for_review_notify_failed",
            skill_id=skill_id, error=str(e),
        )

    return SkillReviewActionResponse(
        skill_id=new_skill.id,
        status=new_skill.status,
        review_state=new_skill.review_state,
        last_action="submit",
        last_reviewer_id=None,
        last_reviewed_at=None,
    )


@router.post(
    "/skills/{skill_id}/review/approve",
    response_model=SkillReviewActionResponse,
)
async def approve_review_endpoint(
    skill_id: str,
    body: SkillReviewApproveRequest,
    session_user: str | None = Depends(get_current_user_id),
) -> SkillReviewActionResponse:
    """Reviewer 批准: review_state=approved + status draft→active.

    ACL (v0.9 T66): 若 X-User-Id header 传入, 校验该 user 在 project 持有
    reviewer 或 owner; backward-compat 兼容老 client (无 header 时降级).
    """
    skill = skill_service.get_skill(skill_id)
    if skill is None:
        raise HTTPException(404, detail="Skill not found")
    if skill.review_state != "pending_review":
        raise HTTPException(
            409,
            detail=(
                f"review_state={skill.review_state}; "
                f"approve 仅在 pending_review 阶段允许"
            ),
        )
    # v0.9 T66 ACL: 优先用 session header (更难伪造) 而非 body.reviewer_id
    effective_reviewer = session_user or body.reviewer_id
    if session_user and session_user != body.reviewer_id:
        # body 与 session 不一致 → 拒 (防 client 伪造)
        raise HTTPException(
            403,
            detail="body.reviewer_id mismatch with X-User-Id session",
        )
    if not membership.can_review(effective_reviewer, skill.project_id):
        raise HTTPException(
            403,
            detail=(
                f"user {effective_reviewer} lacks reviewer role for "
                f"project {skill.project_id}"
            ),
        )
    try:
        new_skill = skill_review.approve(
            skill, reviewer_id=body.reviewer_id, note=body.note
        )
    except skill_review.InvalidReviewTransition as e:
        raise HTTPException(409, detail=str(e)) from e

    skill_service.get_registry().update(new_skill)
    # 通知作者 (latest submit record 里的 reviewer_id 就是作者)
    try:
        from app.services.skill import review_notifier
        author = _find_submit_author(new_skill)
        if author and author != body.reviewer_id:
            review_notifier.notify_review_decision(
                new_skill,
                type_="skill_review_approved",
                author_user_id=author,
                reviewer_id=body.reviewer_id,
            )
    except Exception as e:
        logger.warning(
            "approve_review_notify_failed",
            skill_id=skill_id, error=str(e),
        )

    return SkillReviewActionResponse(
        skill_id=new_skill.id,
        status=new_skill.status,
        review_state=new_skill.review_state,
        last_action="approve",
        last_reviewer_id=new_skill.last_reviewer_id,
        last_reviewed_at=new_skill.last_reviewed_at,
    )


@router.post(
    "/skills/{skill_id}/review/reject",
    response_model=SkillReviewActionResponse,
)
async def reject_review_endpoint(
    skill_id: str,
    body: SkillReviewRejectRequest,
    session_user: str | None = Depends(get_current_user_id),
) -> SkillReviewActionResponse:
    """Reviewer 拒绝: review_state=rejected; status 保留 draft.

    ACL: 同 approve_review_endpoint.
    """
    skill = skill_service.get_skill(skill_id)
    if skill is None:
        raise HTTPException(404, detail="Skill not found")
    if skill.review_state != "pending_review":
        raise HTTPException(
            409,
            detail=(
                f"review_state={skill.review_state}; "
                f"reject 仅在 pending_review 阶段允许"
            ),
        )
    effective_reviewer = session_user or body.reviewer_id
    if session_user and session_user != body.reviewer_id:
        raise HTTPException(
            403,
            detail="body.reviewer_id mismatch with X-User-Id session",
        )
    if not membership.can_review(effective_reviewer, skill.project_id):
        raise HTTPException(
            403,
            detail=(
                f"user {effective_reviewer} lacks reviewer role for "
                f"project {skill.project_id}"
            ),
        )
    try:
        new_skill = skill_review.reject(
            skill, reviewer_id=body.reviewer_id, reason=body.reason
        )
    except skill_review.InvalidReviewTransition as e:
        raise HTTPException(409, detail=str(e)) from e

    skill_service.get_registry().update(new_skill)
    try:
        from app.services.skill import review_notifier
        author = _find_submit_author(new_skill)
        if author and author != body.reviewer_id:
            review_notifier.notify_review_decision(
                new_skill,
                type_="skill_review_rejected",
                author_user_id=author,
                reviewer_id=body.reviewer_id,
                reason=body.reason,
            )
    except Exception as e:
        logger.warning(
            "reject_review_notify_failed",
            skill_id=skill_id, error=str(e),
        )

    return SkillReviewActionResponse(
        skill_id=new_skill.id,
        status=new_skill.status,
        review_state=new_skill.review_state,
        last_action="reject",
        last_reviewer_id=new_skill.last_reviewer_id,
        last_reviewed_at=new_skill.last_reviewed_at,
    )


# ─── v1.0.0 · Marketplace endpoints (T68-T69) ──────────────────


@router.get("/marketplace/skills", response_model=MarketplaceListResponse)
async def list_marketplace_skills(
    q: str | None = Query(default=None, max_length=200),
    min_trust: float = Query(default=0.0, ge=0.0, le=1.0),
    limit: int = Query(default=50, ge=1, le=200),
) -> MarketplaceListResponse:
    """跨 project 列 visibility=public 的 skill, 按 published_at DESC."""
    raw = skill_marketplace.list_marketplace(
        q=q, min_trust=min_trust, limit=limit
    )
    items = [MarketplaceSkillCard(**r) for r in raw]
    return MarketplaceListResponse(items=items, total=len(items))


@router.post(
    "/skills/{skill_id}/publish",
    response_model=SkillPublishResponse,
)
async def publish_skill_endpoint(
    skill_id: str,
    actor_id: str = Depends(require_user_id),
) -> SkillPublishResponse:
    """把 skill 发布到 Marketplace. 仅 owner 可操作.

    前置: status=active + review_state=approved.
    """
    skill = skill_service.get_skill(skill_id)
    if skill is None:
        raise HTTPException(404, detail="Skill not found")
    if not membership.is_owner(actor_id, skill.project_id):
        raise HTTPException(
            403,
            detail=f"Only project owner can publish skill {skill_id}",
        )
    try:
        new_skill = skill_marketplace.publish_public(skill)
    except skill_marketplace.MarketplaceError as e:
        raise HTTPException(409, detail=str(e)) from e

    skill_service.get_registry().update(new_skill)
    logger.info(
        "skill_published",
        skill_id=skill_id, project_id=skill.project_id, actor=actor_id,
    )
    return SkillPublishResponse(
        skill_id=new_skill.id,
        visibility=new_skill.visibility,
        published_at=new_skill.published_at,
    )


@router.post(
    "/skills/{skill_id}/unpublish",
    response_model=SkillPublishResponse,
)
async def unpublish_skill_endpoint(
    skill_id: str,
    actor_id: str = Depends(require_user_id),
) -> SkillPublishResponse:
    """从 Marketplace 撤回 (visibility → private). 仅 owner."""
    skill = skill_service.get_skill(skill_id)
    if skill is None:
        raise HTTPException(404, detail="Skill not found")
    if not membership.is_owner(actor_id, skill.project_id):
        raise HTTPException(
            403,
            detail=f"Only project owner can unpublish skill {skill_id}",
        )
    new_skill = skill_marketplace.unpublish(skill)
    skill_service.get_registry().update(new_skill)
    logger.info(
        "skill_unpublished",
        skill_id=skill_id, project_id=skill.project_id, actor=actor_id,
    )
    return SkillPublishResponse(
        skill_id=new_skill.id,
        visibility=new_skill.visibility,
        published_at=None,
    )


@router.post(
    "/projects/{project_id}/skills/import",
    response_model=Skill,
    status_code=201,
)
async def import_skill_endpoint(
    project_id: str,
    body: SkillImportRequest,
    actor_id: str = Depends(require_user_id),
) -> Skill:
    """从 marketplace 复制 1 个 public skill 到本 project.

    需 actor 是 target_project 的 contributor 以上 (含 owner/reviewer).
    新 skill: status=draft + review_state=not_submitted, 待本 project 审批.
    """
    if not membership.can_contribute(actor_id, project_id):
        raise HTTPException(
            403,
            detail=(
                f"user {actor_id} lacks contributor role for "
                f"project {project_id}"
            ),
        )
    source = skill_service.get_skill(body.source_skill_id)
    if source is None:
        raise HTTPException(404, detail="Source skill not found")
    try:
        new_skill = skill_marketplace.import_skill(
            source_skill=source,
            target_project_id=project_id,
            name_hint=body.name_hint,
        )
    except skill_marketplace.MarketplaceError as e:
        raise HTTPException(409, detail=str(e)) from e

    skill_service.get_registry().add(new_skill)
    # v1.0.1 (review fix): import 后 embedding=None, 异步触发重算
    # 避免 select_skills_for_chapter 排序 score=0 (空 embedding 跳过)
    try:
        import asyncio
        from app.services.skill_service import embed_batch

        async def _reembed() -> None:
            try:
                vectors = await embed_batch([new_skill.skill_md])
                if vectors:
                    updated = new_skill.model_copy(
                        update={"embedding": vectors[0]}
                    )
                    skill_service.get_registry().update(updated)
                    logger.info(
                        "skill_import_embedding_done",
                        skill_id=new_skill.id,
                        embedding_dim=len(vectors[0]),
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "skill_import_embedding_failed",
                    skill_id=new_skill.id, error=str(e),
                )

        asyncio.create_task(_reembed())
    except Exception as e:  # noqa: BLE001
        # embed_batch 可能未导入 (e.g. unit test 环境); 不阻断 import
        logger.warning(
            "skill_import_embedding_skip", skill_id=new_skill.id, error=str(e)
        )

    logger.info(
        "skill_imported",
        new_skill_id=new_skill.id,
        source_skill_id=source.id,
        source_project=source.project_id,
        target_project=project_id,
        actor=actor_id,
    )
    return new_skill


def _find_submit_author(skill: Skill) -> str | None:
    """从 review_history 倒序找最近一次 submit action 的 reviewer_id (= 作者)."""
    for r in reversed(skill.review_history):
        if r.action == "submit":
            return r.reviewer_id
    return None


# ─── v0.8.0 · Governance dashboard endpoints (T62) ─────────────


@router.get(
    "/projects/{project_id}/skills/governance",
    response_model=SkillGovernanceSummary,
)
async def get_governance_summary(project_id: str) -> SkillGovernanceSummary:
    """项目级 Skill 池总览 (前端 dashboard 卡片)."""
    summary = skill_pool.build_governance_summary(project_id)
    return SkillGovernanceSummary(**summary)


@router.get(
    "/skills/{skill_id}/evolve-chain",
    response_model=SkillEvolveChainResponse,
)
async def get_evolve_chain(skill_id: str) -> SkillEvolveChainResponse:
    """Skill 的 parent → current → children 进化链 (按 version 升序)."""
    if skill_service.get_skill(skill_id) is None:
        raise HTTPException(404, detail="Skill not found")
    nodes = skill_pool.build_evolve_chain(skill_id)
    return SkillEvolveChainResponse(skill_id=skill_id, nodes=nodes)


@router.post("/projects/{project_id}/skills/governance/run-trust-recompute")
async def trigger_trust_recompute(project_id: str) -> dict[str, int]:
    """手动触发 trust_score 重算 (T61 job 的手动入口).

    project_id 暂用于 scope log; 实际 recompute 是全量 (跨 project 在单进程内).
    """
    result = skill_pool.recompute_all_trust_scores()
    logger.info(
        "governance_manual_trust_recompute",
        project_id=project_id,
        **result,
    )
    return result


@router.post("/projects/{project_id}/skills/governance/run-deprecation-sweep")
async def trigger_deprecation_sweep(project_id: str) -> dict[str, int]:
    """手动触发 dormant/low_trust deprecation (T60 job 的手动入口)."""
    from app.services.auto_trigger.jobs import skill_deprecation_sweep_job

    await skill_deprecation_sweep_job()
    # 不返单 project 计数, 返"已触发"信号
    candidates = skill_pool.collect_deprecation_candidates()
    remaining = sum(1 for c in candidates if c["project_id"] == project_id)
    return {"remaining_candidates": remaining}


# ─── 辅助 ───────────────────────────────────────────────────


def _collect_source_chapters(
    project_id: str, chapter_ids: list[str]
) -> list[dict]:
    """从 generation_service 内存找到 chapter dumps; 过滤掉不属于此 project_id 的."""
    out: list[dict] = []
    for asset_id, chapters in generation_service._chapters.items():
        asset = generation_service._assets.get(asset_id)
        if asset is None or asset.project_id != project_id:
            continue
        for ch in chapters:
            if ch.id in chapter_ids:
                out.append(ch.model_dump(mode="json"))
    return out


def _collect_failing_chapters(project_id: str, skill_id: str) -> list[dict]:
    """找出: chapter 应用过此 skill 且 approval_state=rejected."""
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
