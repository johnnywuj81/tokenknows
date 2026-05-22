"""EventEvaluator · v0.4.1 (T40).

对应 cron_evaluator (T29) 之于 mode='cron' 规则; 本模块处理 mode='event' 规则.

调用入口:
- GitHub webhook (app/gateway/http_api/webhooks.py) 收到 PR/Issue 事件 →
  归一化为 GitHubEvent → 调 evaluate_github_event(event, project_id)
- 命中后走与 cron evaluator 完全一致的下游 (schedule_execution + 5min 撤回)

EventMatch 字段语义:
- event_type: 字符串相等 (必填; e.g. 'github_pr_merged')
- label_any: GitHub PR/Issue labels 至少一个匹配 (空列表 = 不校验)
- file_glob: 至少一个 file_glob fnmatch 命中 PR files (仅 PR; 空列表 = 不校验)
- title_contains: title 含任一字符串 (大小写不敏感)

不在范围:
- IM signal 触发的 event 规则 (v0.4.2 与 IM SignalGate 一起做)
- 自定义事件源 (后端扩展点)
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from app.config.logging import logger
from app.schemas.auto_trigger import (
    EventMatch,
    TriggerEvaluation,
    TriggerRule,
    TriggerSignal,
)
from app.services import auto_trigger_service as svc


GitHubEventType = Literal[
    "github_pr_opened",
    "github_pr_merged",
    "github_pr_closed",
    "github_pr_synchronize",
    "github_issue_opened",
    "github_issue_closed",
    "github_issue_reopened",
    "github_push",
]


@dataclass(frozen=True)
class GitHubEvent:
    """归一化后的 GitHub 事件 (webhook handler 构造).

    设计目标: EventEvaluator 与 GitHub raw payload schema 解耦.
    """
    event_type: GitHubEventType
    repo: str
    number: int | None = None         # PR/Issue 编号; push 时 None
    title: str = ""
    labels: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def _match_event(event: GitHubEvent, em: EventMatch) -> tuple[bool, str | None]:
    """评估单条 event 是否匹配 EventMatch.

    Returns (matched, reason_if_not_matched).
    """
    if em.event_type != event.event_type:
        return False, f"event_type 不匹配 (rule={em.event_type}, event={event.event_type})"

    if em.label_any:
        event_labels = {lbl.lower() for lbl in event.labels}
        rule_labels = {lbl.lower() for lbl in em.label_any}
        if not (event_labels & rule_labels):
            return False, f"labels 无交集 (rule={em.label_any}, event={event.labels})"

    if em.file_glob:
        ok = False
        for f in event.files_changed:
            for pattern in em.file_glob:
                if fnmatch.fnmatch(f, pattern):
                    ok = True
                    break
            if ok:
                break
        if not ok:
            return False, f"file_glob 无匹配 (patterns={em.file_glob})"

    if em.title_contains:
        title_lower = event.title.lower()
        if not any(s.lower() in title_lower for s in em.title_contains):
            return False, f"title 不含任一关键词 (keywords={em.title_contains})"

    return True, None


def _build_signal(event: GitHubEvent, rule: TriggerRule) -> TriggerSignal:
    """构造 trigger_execution.signal payload (Proposal §7.2 AT-B.1)."""
    label_str = (
        f" · labels: {', '.join(event.labels)}" if event.labels else ""
    )
    summary = f"GitHub {event.event_type} · {event.repo}"
    if event.number is not None:
        summary += f" · #{event.number}"
    if event.title:
        summary += f" · {event.title[:80]}"
    summary += label_str

    return TriggerSignal(
        type="github_webhook",
        event_id=f"{event.event_type}:{event.repo}:{event.number or 'push'}",
        summary=summary,
        payload={
            "event_type": event.event_type,
            "repo": event.repo,
            "number": event.number,
            "title": event.title,
            "labels": event.labels,
            "rule_id": rule.id,
        },
    )


def evaluate_github_event(
    event: GitHubEvent,
    project_id: str,
    *,
    withdraw_window_min: float = svc.DEFAULT_WITHDRAW_WINDOW_MIN,
) -> dict[str, int]:
    """评估所有 enabled mode=event 规则; 命中即 schedule.

    Returns 评估统计 dict.
    """
    rules = svc.list_all_rules(enabled=True, mode="event")
    stats = {
        "rules_evaluated": 0,
        "matched": 0,
        "scheduled": 0,
        "skipped_cooldown": 0,
        "skipped_daily_cap": 0,
        "skipped_no_match": 0,
        "errors": 0,
    }
    now = datetime.now(timezone.utc)

    # 按 priority DESC; 同类型 (asset_type) 同 event 只取最高优先级
    rules_sorted = sorted(rules, key=lambda r: -r.priority)
    fired_asset_types: set[str] = set()

    for rule in rules_sorted:
        stats["rules_evaluated"] += 1
        if rule.event_match is None:
            continue

        matched, why_not = _match_event(event, rule.event_match)
        if not matched:
            logger.debug(
                "auto_trigger_event_skipped_no_match",
                rule_id=rule.id, reason=why_not,
            )
            stats["skipped_no_match"] += 1
            continue

        # 同 event 已被更高 priority 规则触发同类型 → 跳过低优先级 (Proposal §5.1)
        if rule.asset_type in fired_asset_types:
            logger.debug(
                "auto_trigger_event_lower_priority_skipped",
                rule_id=rule.id, asset_type=rule.asset_type,
            )
            continue
        stats["matched"] += 1

        signal = _build_signal(event, rule)
        try:
            _evaluate_for_project(
                rule, project_id, signal, now,
                withdraw_window_min, stats, fired_asset_types,
            )
        except Exception as e:
            logger.error(
                "auto_trigger_event_evaluate_failed",
                rule_id=rule.id, project_id=project_id, error=str(e),
            )
            stats["errors"] += 1

    logger.info(
        "auto_trigger_event_evaluator_done",
        event_type=event.event_type,
        project_id=project_id,
        **stats,
    )
    return stats


def _evaluate_for_project(
    rule: TriggerRule,
    project_id: str,
    signal: TriggerSignal,
    now: datetime,
    withdraw_window_min: float,
    stats: dict[str, int],
    fired_asset_types: set[str],
) -> None:
    """单 (rule, project) 评估; 命中 → schedule; cooldown/daily_cap 失败 → record_skip."""
    from datetime import timedelta

    # cooldown
    if rule.cooldown_seconds > 0:
        since = now - timedelta(seconds=rule.cooldown_seconds)
        if svc.count_fired_since(rule.id, since) > 0:
            svc.record_skip(
                rule, project_id, signal, "cooldown",
                evaluation=TriggerEvaluation(matched=True, confidence=1.0),
            )
            stats["skipped_cooldown"] += 1
            return

    # daily_cap
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    if svc.count_fired_since(rule.id, today_start) >= rule.daily_cap:
        svc.record_skip(
            rule, project_id, signal, "daily_cap_reached",
            evaluation=TriggerEvaluation(matched=True, confidence=1.0),
        )
        stats["skipped_daily_cap"] += 1
        return

    # 全过 → schedule (5 min 撤回窗口)
    svc.schedule_execution(
        rule, project_id, signal,
        withdraw_window_min=withdraw_window_min,
        evaluation=TriggerEvaluation(matched=True, confidence=1.0),
    )
    stats["scheduled"] += 1
    fired_asset_types.add(rule.asset_type)


# ─── webhook → GitHubEvent 归一化 helper (供 webhook handler 调) ──


def normalize_pr_webhook(payload: dict[str, Any]) -> GitHubEvent | None:
    """pull_request webhook payload → GitHubEvent.

    返回 None 表示该 action 不被规则系统关心 (e.g. labeled / assigned).
    """
    action = payload.get("action")
    pr = payload.get("pull_request") or {}
    repo = (payload.get("repository") or {}).get("full_name") or "unknown"

    if action == "opened":
        event_type: GitHubEventType = "github_pr_opened"
    elif action == "synchronize":
        event_type = "github_pr_synchronize"
    elif action == "closed":
        event_type = (
            "github_pr_merged" if pr.get("merged") else "github_pr_closed"
        )
    else:
        return None  # ignore labeled / assigned / review_requested 等

    labels = [lbl.get("name") for lbl in pr.get("labels") or [] if lbl.get("name")]
    # files_changed 在 pull_request 主 payload 里没有; GitHub 需要单独调 /pulls/:n/files API
    # v0.4.1 暂不调; 后续若要 file_glob 真支持, 在 webhook handler 内 fetch
    return GitHubEvent(
        event_type=event_type,
        repo=repo,
        number=pr.get("number"),
        title=pr.get("title") or "",
        labels=labels,
        files_changed=[],
        raw=payload,
    )


def normalize_issue_webhook(payload: dict[str, Any]) -> GitHubEvent | None:
    action = payload.get("action")
    issue = payload.get("issue") or {}
    if issue.get("pull_request"):
        return None  # issue endpoint 把 PR comment 也吐出来; 跳过

    repo = (payload.get("repository") or {}).get("full_name") or "unknown"

    if action == "opened":
        event_type: GitHubEventType = "github_issue_opened"
    elif action == "closed":
        event_type = "github_issue_closed"
    elif action == "reopened":
        event_type = "github_issue_reopened"
    else:
        return None  # edited / assigned 等不触发

    labels = [lbl.get("name") for lbl in issue.get("labels") or [] if lbl.get("name")]
    return GitHubEvent(
        event_type=event_type,
        repo=repo,
        number=issue.get("number"),
        title=issue.get("title") or "",
        labels=labels,
        files_changed=[],
        raw=payload,
    )


__all__ = [
    "GitHubEvent",
    "GitHubEventType",
    "evaluate_github_event",
    "normalize_pr_webhook",
    "normalize_issue_webhook",
]
