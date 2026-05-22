"""HTTP API · v0.4 · 自动触发规则 + 执行历史 (T32).

端点 (4 组 9 个):
    GET    /projects/:pid/auto-triggers/rules                  列规则 (filter enabled/mode)
    GET    /projects/:pid/auto-triggers/rules/:rid             单条规则
    PATCH  /projects/:pid/auto-triggers/rules/:rid             启停 / priority / cooldown 等
    GET    /projects/:pid/auto-triggers/executions             历史 (filter rule_id/status/limit)
    GET    /projects/:pid/auto-triggers/executions/:eid        单条执行详情
    POST   /projects/:pid/auto-triggers/executions/:eid/cancel
           撤回 (仅 status=scheduled 时合法; fired 等返 409)
    POST   /projects/:pid/auto-triggers/executions/:eid/flag-false-positive
           用户报告误触发 (不改 status, 仅标 flag)
    GET    /projects/:pid/auto-triggers/onboarding             预置规则预览 (引导向导用)
    POST   /projects/:pid/auto-triggers/onboarding             批量启用/停用预置规则

权限 (v0.4.0 简化版, 与 IM/Skills 一致, 未做 RBAC):
- 所有端点对 project 成员可见; UI 二次校验 Owner / Editor 权限
- 后续 v0.4.3 加 RBAC 时本文件不需大改

设计依据:
- Proposal §10 API 设计
- 前端 mocks/handlers/auto-triggers.ts (反向契约, 真接后端时无需改前端)
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ValidationError

from app.config.logging import logger
from app.schemas.auto_trigger import (
    EventMatch,
    ExtraCondition,
    ThresholdSpec,
    TriggerExecution,
    TriggerMode,
    TriggerRule,
    TriggerSignal as TriggerSignalDTO,
)
from app.services import auto_trigger_service as svc

router = APIRouter()


# ─── Response wrappers ────────────────────────────────────


class RuleListResponse(BaseModel):
    """对齐前端 useQuery 期望的 { data: [...] } 信封."""
    data: list[TriggerRule]


class ExecutionListResponse(BaseModel):
    data: list[TriggerExecution]


class OnboardingPreviewResponse(BaseModel):
    default_rules: list[TriggerRule]


class OnboardingEnableRequest(BaseModel):
    enabled_rule_ids: list[str]


class OnboardingEnableResponse(BaseModel):
    enabled_count: int
    skipped_count: int


class TestFireResponse(BaseModel):
    """POST .../rules/:rid/test-fire 响应; 体验要素 #30 演示用."""
    execution: TriggerExecution
    note: str = (
        "Demo: 撤回窗口缩短为 30 秒, 方便演示. 真实自动触发用 5 分钟撤回窗口."
    )


# ─── Request schemas ──────────────────────────────────────


class RulePatchRequest(BaseModel):
    """部分更新 rule. UI 主要场景: 启停 + 调 priority / cooldown."""
    enabled: bool | None = None
    priority: int | None = None
    cooldown_seconds: int | None = None
    daily_cap: int | None = None
    description: str | None = None
    cron_expr: str | None = None
    event_match: EventMatch | None = None
    threshold_spec: ThresholdSpec | None = None
    extra_condition: ExtraCondition | None = None


class RuleCreateRequest(BaseModel):
    """T43 v0.4.3 · UI builder 新建规则 (项目级).

    强制字段: name / mode / asset_type; 各 mode 对应 spec 必填.
    """
    name: str
    mode: Literal["cron", "event", "threshold", "mention"]
    asset_type: str
    description: str = ""
    priority: int = 50
    enabled: bool = True
    cooldown_seconds: int = 3600
    daily_cap: int = 5
    cron_expr: str | None = None
    event_match: EventMatch | None = None
    threshold_spec: ThresholdSpec | None = None
    extra_condition: ExtraCondition | None = None


# ─── Rules CRUD ───────────────────────────────────────────


@router.post(
    "/projects/{project_id}/auto-triggers/rules",
    response_model=TriggerRule,
    status_code=201,
)
async def create_auto_trigger_rule(
    project_id: str,
    body: RuleCreateRequest,
) -> TriggerRule:
    """v0.4.3 UI builder · 创建项目级规则.

    规则归属当前 project_id (不允许通过此 API 创建实例级规则;
    实例级由 seeder 在启动时自动 seed).
    返回 201 + 新建的规则.
    """
    try:
        return svc.create_rule(
            project_id=project_id,
            name=body.name,
            mode=body.mode,
            asset_type=body.asset_type,
            created_by="ui_user",  # v0.4.3 简化: 不接入鉴权; v0.5 RBAC 时填真 user_id
            description=body.description,
            priority=body.priority,
            enabled=body.enabled,
            cooldown_seconds=body.cooldown_seconds,
            daily_cap=body.daily_cap,
            cron_expr=body.cron_expr,
            event_match=body.event_match,
            threshold_spec=body.threshold_spec,
            extra_condition=body.extra_condition,
        )
    except svc.RuleSpecMismatch as e:
        # e.g. mode=cron 但 cron_expr 缺
        raise HTTPException(400, detail=str(e)) from e
    except ValidationError as e:
        # Pydantic 字段约束 (e.g. cooldown_seconds < 60, priority 越界) 触达 TriggerRule model
        raise HTTPException(400, detail=f"字段校验失败: {e.errors()[0]['msg']}") from e


@router.delete(
    "/projects/{project_id}/auto-triggers/rules/{rule_id}",
    status_code=204,
)
async def delete_auto_trigger_rule(
    project_id: str,
    rule_id: str,
) -> None:
    """删除规则; FK CASCADE 同步清理 trigger_executions.

    限制:
    - 实例级规则 (project_id=NULL) 不允许通过此 API 删 (避免误删全实例默认规则);
      Owner 想去掉只能 PATCH enabled=false
    - 跨项目访问返 404
    """
    rule = svc.get_rule(rule_id)
    if rule is None:
        raise HTTPException(404, detail="rule not found")
    if rule.project_id is None:
        raise HTTPException(
            403,
            detail="实例级默认规则不可删除; 请改用 PATCH 设 enabled=false",
        )
    if rule.project_id != project_id:
        raise HTTPException(404, detail="rule not found")
    ok = svc.delete_rule(rule_id)
    if not ok:
        # 罕见: 并发删除
        raise HTTPException(404, detail="rule not found")


@router.get(
    "/projects/{project_id}/auto-triggers/rules",
    response_model=RuleListResponse,
)
async def list_auto_trigger_rules(
    project_id: str,
    enabled: bool | None = Query(None, description="仅启用 / 仅暂停; None=不过滤"),
    mode: Literal["cron", "event", "threshold", "mention"] | None = Query(None),
) -> RuleListResponse:
    """列出项目可见的所有规则 (实例级默认 + 项目级自定义).

    返回按 priority DESC + updated_at DESC 排序.
    """
    rules = svc.list_rules(
        project_id=project_id,
        enabled=enabled,
        mode=mode,
        include_instance_defaults=True,
    )
    return RuleListResponse(data=rules)


@router.get(
    "/projects/{project_id}/auto-triggers/rules/{rule_id}",
    response_model=TriggerRule,
)
async def get_auto_trigger_rule(project_id: str, rule_id: str) -> TriggerRule:
    rule = svc.get_rule(rule_id)
    if rule is None:
        raise HTTPException(404, detail="rule not found")
    # 实例级规则 (project_id=None) 对所有项目可见; 项目级要求 project 匹配
    if rule.project_id is not None and rule.project_id != project_id:
        raise HTTPException(404, detail="rule not found")
    return rule


@router.patch(
    "/projects/{project_id}/auto-triggers/rules/{rule_id}",
    response_model=TriggerRule,
)
async def patch_auto_trigger_rule(
    project_id: str,
    rule_id: str,
    body: RulePatchRequest,
) -> TriggerRule:
    """启停 / 改 priority / cooldown / spec.

    实例级规则 (project_id=None) 可被任意项目调用此端点修改 (Q6 决策: 项目级覆盖
    场景下, 用户对实例级规则的改动会被记到该规则上, 影响所有项目;
    v0.4.0 简化处理, v0.4.3 完整版会拆分 fork 语义).
    """
    rule = svc.get_rule(rule_id)
    if rule is None:
        raise HTTPException(404, detail="rule not found")
    if rule.project_id is not None and rule.project_id != project_id:
        raise HTTPException(404, detail="rule not found")

    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return rule  # 无变更
    try:
        return svc.update_rule(rule_id, **changes)
    except svc.RuleSpecMismatch as e:
        raise HTTPException(400, detail=str(e)) from e
    except svc.RuleNotFound as e:
        raise HTTPException(404, detail=str(e)) from e


# ─── Executions ───────────────────────────────────────────


@router.get(
    "/projects/{project_id}/auto-triggers/executions",
    response_model=ExecutionListResponse,
)
async def list_auto_trigger_executions(
    project_id: str,
    rule_id: str | None = Query(None),
    status: Literal[
        "scheduled", "fired", "canceled", "skipped", "failed", "expired"
    ] | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> ExecutionListResponse:
    """项目执行历史 (时间轴; 体验要素 #31).

    按 created_at DESC 排序; 默认最多 50 条.
    """
    executions = svc.list_executions(
        project_id=project_id,
        rule_id=rule_id,
        status=status,
        limit=limit,
    )
    return ExecutionListResponse(data=executions)


@router.get(
    "/projects/{project_id}/auto-triggers/executions/{execution_id}",
    response_model=TriggerExecution,
)
async def get_auto_trigger_execution(
    project_id: str, execution_id: str
) -> TriggerExecution:
    exe = svc.get_execution(execution_id)
    if exe is None:
        raise HTTPException(404, detail="execution not found")
    if exe.project_id != project_id:
        raise HTTPException(404, detail="execution not found")
    return exe


@router.post(
    "/projects/{project_id}/auto-triggers/executions/{execution_id}/cancel",
    response_model=TriggerExecution,
)
async def cancel_auto_trigger_execution(
    project_id: str, execution_id: str
) -> TriggerExecution:
    """撤回窗口期内取消 scheduled 执行 (体验要素 #30 必经路径).

    409 Conflict: status != 'scheduled' (已 fired / canceled / failed 等).
    """
    exe = svc.get_execution(execution_id)
    if exe is None:
        raise HTTPException(404, detail="execution not found")
    if exe.project_id != project_id:
        raise HTTPException(404, detail="execution not found")
    if exe.status != "scheduled":
        raise HTTPException(
            409, detail=f"仅 scheduled 状态可撤回 (current={exe.status})"
        )
    try:
        return svc.cancel_execution(execution_id, by_user=True)
    except svc.InvalidTransition as e:
        # 并发场景: 上面 check 后, dispatcher 抢先 fire
        raise HTTPException(409, detail=str(e)) from e


@router.post(
    "/projects/{project_id}/auto-triggers/executions/{execution_id}/flag-false-positive",
    response_model=TriggerExecution,
)
async def flag_auto_trigger_false_positive(
    project_id: str, execution_id: str
) -> TriggerExecution:
    """用户报告误触发. 不改 status; 仅标 user_flagged_false_positive=true.

    可在任意状态下标记 (包括已 fired 的 asset 事后发现是误触发).
    累积 ≥ 5 个同规则误触发 → 后续 UI 提示 Owner "是否调整阈值" (v0.4.3).
    """
    exe = svc.get_execution(execution_id)
    if exe is None:
        raise HTTPException(404, detail="execution not found")
    if exe.project_id != project_id:
        raise HTTPException(404, detail="execution not found")
    return svc.flag_false_positive(execution_id)


# ─── Demo: test-fire (体验要素 #30 撤回窗口演示) ────────


@router.post(
    "/projects/{project_id}/auto-triggers/rules/{rule_id}/test-fire",
    response_model=TestFireResponse,
)
async def test_fire_auto_trigger_rule(
    project_id: str,
    rule_id: str,
) -> TestFireResponse:
    """立即创建一条 scheduled execution, 撤回窗口缩短到 30 秒 (demo 用).

    用途:
    - 体验要素 #30 浮动撤回通知卡演示: 真实场景 cron 5min, 太长不好演示;
      此 endpoint 让用户能立即触发完整流程
    - 用户点 30s 内取消 → 通知卡变红消失, LLM 不调
    - 不点 → withdraw_window_resolver 自动 fire → asset 入库 (含 trigger_meta)

    简化策略 (v0.4.0 demo only):
    - 不做权限校验 (与其他 endpoint 一致)
    - 不限频 (生产用 cooldown_seconds; demo 不约束)
    - signal 标 type='manual_test_fire' 便于审计区分
    """
    rule = svc.get_rule(rule_id)
    if rule is None:
        raise HTTPException(404, detail="rule not found")
    if rule.project_id is not None and rule.project_id != project_id:
        raise HTTPException(404, detail="rule not found")

    signal = TriggerSignalDTO(
        type="manual_test_fire",
        summary=f"[Demo] 立即触发演示 · {rule.name}",
        payload={"demo": True, "withdraw_window_sec": 30},
    )
    exe = svc.schedule_execution(
        rule, project_id, signal=signal, withdraw_window_min=0.5  # 30s
    )
    logger.info(
        "auto_trigger_test_fire",
        rule_id=rule.id,
        project_id=project_id,
        execution_id=exe.id,
    )
    return TestFireResponse(execution=exe)


# ─── Onboarding (引导向导, 体验要素 #35) ─────────────────


@router.get(
    "/projects/{project_id}/auto-triggers/onboarding",
    response_model=OnboardingPreviewResponse,
)
async def get_auto_trigger_onboarding(project_id: str) -> OnboardingPreviewResponse:
    """返回项目可见的所有规则 (实例级默认 + 项目级), 用于引导向导卡片渲染.

    与 list_rules 区别: 前端用 onboarding 端点表达"展示给首次用户"的语义,
    便于未来加 onboarding 专属字段 (如 recommendation_score / 视频教程链接 等).
    v0.4.0 直接返回 rules.
    """
    rules = svc.list_rules(
        project_id=project_id,
        include_instance_defaults=True,
    )
    return OnboardingPreviewResponse(default_rules=rules)


@router.post(
    "/projects/{project_id}/auto-triggers/onboarding",
    response_model=OnboardingEnableResponse,
)
async def enable_auto_trigger_onboarding(
    project_id: str,
    body: OnboardingEnableRequest,
) -> OnboardingEnableResponse:
    """一键启用选中的预置规则; 未选中的设为 disabled.

    实际是对每条规则调 update_rule(enabled=...).
    """
    enabled_set = set(body.enabled_rule_ids)
    all_rules = svc.list_rules(project_id=project_id, include_instance_defaults=True)

    enabled_count = 0
    skipped_count = 0
    for rule in all_rules:
        should_enable = rule.id in enabled_set
        try:
            svc.update_rule(rule.id, enabled=should_enable)
            if should_enable:
                enabled_count += 1
            else:
                skipped_count += 1
        except svc.RuleNotFound:
            # 罕见: 规则刚被并发删除
            logger.warning(
                "auto_trigger_onboarding_rule_missing",
                rule_id=rule.id,
                project_id=project_id,
            )

    logger.info(
        "auto_trigger_onboarding_applied",
        project_id=project_id,
        enabled=enabled_count,
        skipped=skipped_count,
    )
    return OnboardingEnableResponse(
        enabled_count=enabled_count,
        skipped_count=skipped_count,
    )
