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

from fastapi import APIRouter, HTTPException

from app.config.logging import logger
from app.schemas.skill import (
    Skill,
    SkillDistillRequest,
    SkillUpdateRequest,
)
from app.services import generation_service, skill_service

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
