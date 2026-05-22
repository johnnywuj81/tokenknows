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

from datetime import datetime, timedelta, timezone
from typing import Any

from app.config.logging import logger
from app.persistence import get_db
from app.schemas.auto_trigger import AssetTriggerMeta, TriggerExecution, TriggerRule
from app.schemas.generation import GenerateAssetRequest
from app.services import auto_trigger_service as svc
from app.services import generation_service, skill_service


# 默认 time_window: 自动触发的 asset 用"上周"窗口
# (与 PRD §5.3 C1 "每周自动生成上周周报" 对齐)
DEFAULT_TIME_WINDOW = "last_7_days"

# T42 IM Skill 蒸馏: 拉最近 N 天 top-K signal 作为蒸馏源
SKILL_DISTILL_DAYS = 30
SKILL_DISTILL_TOP_K = 20

# T44 v0.4.4 · 按 asset_type 估算 token 用量 (用于月配额记账)
# 真实 token 用量后续可从 generation_service / litellm 拿
TOKEN_ESTIMATES_PER_TYPE = {
    "weekly_report": 5000,
    "tech_design": 8000,
    "adr": 4000,
    "incident": 4000,
    "book": 50000,
    "agent_skill": 2000,
}
TOKEN_ESTIMATE_DEFAULT = 5000


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

    # 4. 类型路由: agent_skill 走 skill_service.distill_skill;
    #    其余走 generation_service.start_generation (T30 标准路径)
    trigger_meta = _build_trigger_meta(rule, execution)
    try:
        if rule.asset_type == "agent_skill":
            artifact_id = await _dispatch_skill_distill(execution, rule, trigger_meta)
        else:
            artifact_id = await _dispatch_generation(execution, rule, trigger_meta)
    except svc.InvalidTransition:
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

    if artifact_id is None:
        # 蒸馏路径: 无 source IM signal → 提前 mark_failed 已经做过
        return None

    # 5. mark fired
    try:
        svc.mark_fired(execution_id, asset_id=artifact_id)
    except svc.InvalidTransition:
        logger.warning(
            "auto_trigger_dispatch_concurrent_transition",
            execution_id=execution_id,
            artifact_id=artifact_id,
        )

    # 6. v0.4.4 · 月配额记账 (估算; 真实 token 用量后续可从 LLM Gateway 拿)
    estimated_tokens = TOKEN_ESTIMATES_PER_TYPE.get(
        rule.asset_type, TOKEN_ESTIMATE_DEFAULT
    )
    try:
        svc.record_token_usage(execution.project_id, estimated_tokens)
    except Exception as e:
        # 记账失败不影响 fire 成功 (asset 已生成)
        logger.error(
            "auto_trigger_quota_record_failed",
            project_id=execution.project_id,
            tokens=estimated_tokens,
            error=str(e),
        )

    logger.info(
        "auto_trigger_dispatch_fired",
        execution_id=execution_id,
        rule_id=rule.id,
        artifact_id=artifact_id,
        asset_type=rule.asset_type,
        estimated_tokens=estimated_tokens,
    )
    return artifact_id


# ─── 类型路由 ─────────────────────────────────────────────


async def _dispatch_generation(
    execution: TriggerExecution,
    rule: TriggerRule,
    trigger_meta: dict,
) -> str | None:
    """T30 标准路径: 走 generation_service.start_generation 5 阶段 pipeline.

    适用于 weekly_report / tech_design / adr / incident / book.
    """
    req = GenerateAssetRequest(
        type=rule.asset_type,
        time_window=DEFAULT_TIME_WINDOW,
    )
    asset = await generation_service.start_generation(
        project_id=execution.project_id,
        req=req,
        user_id="system",
        trigger_meta=trigger_meta,
    )
    return asset.id


def _build_fake_chapter_from_signals(
    project_id: str, signals: list[dict[str, Any]]
) -> dict[str, Any]:
    """把 IM signal messages 包装成 1 个 fake chapter dump 喂给 skill_service.distill_skill.

    distill_skill 期望的 chapter dump: { id, title, content, regeneration_history?, ... }
    """
    lines: list[str] = [
        f"# IM 信号汇编 (项目 {project_id})",
        "",
        f"来源: 近 {SKILL_DISTILL_DAYS} 天 SignalGate 标记的高价值消息 (top {len(signals)})",
        "",
    ]
    for i, m in enumerate(signals, 1):
        sender = m.get("sender", {}) if isinstance(m.get("sender"), dict) else {}
        sender_name = sender.get("name") or sender.get("user_id") or "?"
        text = (
            m.get("text")
            or m.get("content")
            or (m.get("body") or {}).get("text")
            or ""
        )
        received_at = m.get("received_at", "")[:19]
        lines.append(f"## §{i} · {sender_name} · {received_at}")
        lines.append("")
        lines.append(text.strip())
        lines.append("")
    content = "\n".join(lines)
    return {
        "id": f"synthetic-im-signals-{project_id}",
        "asset_id": "synthetic",
        "order_index": 0,
        "title": f"IM 信号汇编 · {project_id}",
        "content": content,
        "approval_state": "approved",  # 蒸馏要求 source 是 approved
        "regeneration_history": [],
    }


async def _dispatch_skill_distill(
    execution: TriggerExecution,
    rule: TriggerRule,
    trigger_meta: dict,
) -> str | None:
    """T42 IM Skill 自动蒸馏: 拉 IM signals → 包装 fake chapter → 调 skill_service.distill_skill.

    返回 skill.id 作为 artifact_id (替代 asset.id).
    """
    since = datetime.now(timezone.utc) - timedelta(days=SKILL_DISTILL_DAYS)
    signals = get_db().list_top_im_signals_in_project(
        execution.project_id,
        since_iso=since.isoformat(),
        limit=SKILL_DISTILL_TOP_K,
    )
    if not signals:
        logger.warning(
            "auto_trigger_skill_distill_no_signals",
            execution_id=execution.id,
            project_id=execution.project_id,
            rule_id=rule.id,
        )
        try:
            svc.mark_failed(execution.id, error="无可用 IM signal source")
        except svc.InvalidTransition:
            pass
        return None

    fake_chapter = _build_fake_chapter_from_signals(execution.project_id, signals)
    name_hint = f"im-distilled-{rule.name[:20]}"
    skill = await skill_service.distill_skill(
        project_id=execution.project_id,
        source_chapters=[fake_chapter],
        name_hint=name_hint,
        project_label=execution.project_id,
    )
    logger.info(
        "auto_trigger_skill_distilled",
        skill_id=skill.id,
        project_id=execution.project_id,
        signals_used=len(signals),
        trigger_meta_rule=trigger_meta.get("rule_name"),
    )
    return skill.id


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
