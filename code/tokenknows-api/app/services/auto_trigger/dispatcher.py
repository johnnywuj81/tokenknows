"""TriggerDispatcher · 把 scheduled execution 真正派遣给 LLM (v0.4 T30).

调用入口: T31 withdraw_window_resolver_job 每 30s 拉一批 fire_at 已过的 scheduled
execution → fire(execution.id) 单次执行.

流程:
1. 加载 execution + rule
2. 双重校验: status='scheduled' (重入安全) + fire_at <= now (撤回窗口已过)
3. 构造 GenerateAssetRequest + AssetTriggerMeta
4. 调 generation_service.start_generation(..., trigger_meta=...)
5. 成功 → mark_fired(exec, asset.id); 失败 → mark_failed(exec, error)

设计原则:
- 不抛异常给 caller (jobs.py 已有 try/except wrapping; 此处吞错并 mark_failed)
- 重入安全: 用 svc._transition (内置 can_transition 状态机校验); 即使 dispatch
  并发 fire 两次同一 execution, 第二次也会因 status 已 != 'scheduled' 被拒
- 不预扣 quota: v0.4.0 不实现 quota check; 仅记录 LLM 用量到现有 egress_log
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config.logging import logger
from app.schemas.auto_trigger import AssetTriggerMeta, TriggerExecution, TriggerRule
from app.schemas.generation import GenerateAssetRequest
from app.services import auto_trigger_service as svc
from app.services import generation_service


# 默认 time_window: 自动触发的 asset 用"上周"窗口
# (与 PRD §5.3 C1 "每周自动生成上周周报" 对齐)
DEFAULT_TIME_WINDOW = "last_7_days"


class DispatcherError(Exception):
    """Dispatcher 业务异常."""


class PrematureFire(DispatcherError):
    """fire_at 还没到 (撤回窗口未结束)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_trigger_meta(rule: TriggerRule, execution: TriggerExecution) -> dict:
    """组装 AssetTriggerMeta → JSON-serializable dict (asset.trigger_meta 用)."""
    meta = AssetTriggerMeta(
        trigger_mode=rule.mode,
        rule_id=rule.id,
        rule_name=rule.name,
        signal=execution.signal,
        confidence=(
            execution.evaluation.confidence
            if execution.evaluation is not None
            else 1.0
        ),
        fired_at=_now(),
        trigger_execution_id=execution.id,
    )
    return meta.model_dump(mode="json")


async def fire(execution_id: str) -> str | None:
    """对一个 scheduled execution 派遣 LLM 生成 asset.

    Returns:
        - asset_id (成功生成的 asset id)
        - None (重入: 已不是 scheduled / fire_at 未到 / 异常已被吞 + mark_failed)
    """
    execution = svc.get_execution(execution_id)
    if execution is None:
        logger.warning("auto_trigger_dispatch_no_execution", execution_id=execution_id)
        return None

    # 1. 重入安全: 不是 scheduled 跳过 (可能已被别处 fire / cancel)
    if execution.status != "scheduled":
        logger.debug(
            "auto_trigger_dispatch_skipped_status",
            execution_id=execution_id,
            current_status=execution.status,
        )
        return None

    # 2. 撤回窗口校验
    if execution.fire_at > _now():
        logger.debug(
            "auto_trigger_dispatch_premature",
            execution_id=execution_id,
            fire_at=execution.fire_at.isoformat(),
        )
        return None

    # 3. 加载规则; 删了 → mark_failed
    rule = svc.get_rule(execution.rule_id)
    if rule is None:
        try:
            svc.mark_failed(execution_id, error=f"规则 {execution.rule_id} 已删除")
        except svc.InvalidTransition:
            pass
        logger.warning(
            "auto_trigger_dispatch_rule_missing",
            execution_id=execution_id,
            rule_id=execution.rule_id,
        )
        return None

    # 4. 构造 GenerateAssetRequest + trigger_meta
    req = GenerateAssetRequest(
        type=rule.asset_type,
        time_window=DEFAULT_TIME_WINDOW,
    )
    trigger_meta = _build_trigger_meta(rule, execution)

    # 5. 调 generation pipeline
    try:
        asset = await generation_service.start_generation(
            project_id=execution.project_id,
            req=req,
            user_id="system",
            trigger_meta=trigger_meta,
        )
    except svc.InvalidTransition:
        # 几乎不会到这里 (状态机已校验), 防御代码
        return None
    except Exception as e:
        logger.error(
            "auto_trigger_dispatch_generation_failed",
            execution_id=execution_id,
            rule_id=rule.id,
            project_id=execution.project_id,
            error=str(e),
            exc_info=True,
        )
        try:
            svc.mark_failed(execution_id, error=str(e))
        except svc.InvalidTransition:
            pass
        return None

    # 6. mark fired
    try:
        svc.mark_fired(execution_id, asset_id=asset.id)
    except svc.InvalidTransition:
        # 并发场景: 别处刚把它转走; asset 已经创建 (留下来等 Reviewer)
        logger.warning(
            "auto_trigger_dispatch_concurrent_transition",
            execution_id=execution_id,
            asset_id=asset.id,
        )
    logger.info(
        "auto_trigger_dispatch_fired",
        execution_id=execution_id,
        rule_id=rule.id,
        asset_id=asset.id,
        asset_type=rule.asset_type,
    )
    return asset.id


async def fire_batch(execution_ids: list[str]) -> dict[str, int]:
    """串行 fire 一批 execution. T31 withdraw_resolver 主调用入口.

    串行而非并行: avoid 同时启动 N 个 LLM 调用打满 token 配额; 也防同一
    rule 被多次 fan-out 时的竞态. v0.4.0 单实例无并发压力, 串行足够.
    """
    stats = {"fired": 0, "skipped": 0, "failed": 0}
    for eid in execution_ids:
        try:
            asset_id = await fire(eid)
            if asset_id is not None:
                stats["fired"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            logger.error(
                "auto_trigger_dispatch_unexpected",
                execution_id=eid,
                error=str(e),
                exc_info=True,
            )
            stats["failed"] += 1
    return stats


__all__ = ["fire", "fire_batch", "DispatcherError", "PrematureFire"]
