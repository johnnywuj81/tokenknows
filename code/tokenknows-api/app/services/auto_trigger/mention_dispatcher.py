"""@ 机器人按需触发 · v0.5.0 (T45-T47).

本文件 v0.5.0 分 3 个 task 渐进填充:
- T45 (已合): 命令解析 + 限频 + Schema helper (纯函数, 无 IO)
- T46 (本提交): IM webhook 接入 + dispatch_mention 主流程 + project resolution
- T47: 群内 thread 回执

设计依据:
- Proposal_OnDemand_and_ContributorConsent_v0.5.md §2.1-2.3 (OD-1/OD-3/OD-4)
- engineering_handoff/tasks/T45-mention-command-parser.md
- engineering_handoff/tasks/T46-mention-dispatcher.md
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import time as dt_time
from typing import Any, Literal

from app.schemas.auto_trigger import TriggerSignal

# ─── 类型定义 (OD-1) ──────────────────────────────────────


Subcommand = Literal["distill", "digest", "skill"]
"""3 个 subcommand:
- distill: 仅入 ValueSegment (不生成 asset)
- digest:  → weekly_report 类型 asset
- skill:   → agent_skill (走 v0.5.1 Q5 同意流程)
"""

WindowPreset = Literal["30m", "2h", "today", "yesterday", "7d"]
"""5 个时间窗口预设 (OD-4 故意限制, 防恶意拉满群历史)."""

VALID_SUBCOMMANDS = frozenset(["distill", "digest", "skill"])
VALID_WINDOWS = frozenset(["30m", "2h", "today", "yesterday", "7d"])

# subcommand → asset_type 映射
SUBCOMMAND_TO_ASSET_TYPE: dict[Subcommand, str] = {
    "distill": "value_segments_only",  # T46 分支特殊处理 (不走 dispatcher.fire)
    "digest": "weekly_report",
    "skill": "agent_skill",
}


@dataclass(frozen=True)
class ParsedMention:
    """已解析的 @ 提及命令."""
    subcommand: Subcommand
    window: WindowPreset
    raw_text: str  # 审计用


class ParseError(Exception):
    """命令文法错误; T46 dispatcher 收到后回简短帮助到群里."""


# ─── 解析 (T45) ───────────────────────────────────────────


def parse_command(text: str) -> ParsedMention:
    """严格 whitelist 解析 `/<subcommand> <window>`.

    输入示例 (text 已被 T46 剥离 @TokenKnows 提及部分):
      "/digest 2h"
      "/distill 30m"
      "/skill today"

    Raises:
        ParseError: 文法不符 (含多空格/缺参数/未知 subcommand/非预设 window).
    """
    if not text or not text.strip():
        raise ParseError("命令为空")

    tokens = text.strip().split()
    if len(tokens) != 2:
        raise ParseError(
            f"格式应为 /<subcommand> <window>, 收到 {len(tokens)} 个 token"
        )

    cmd, window = tokens
    if not cmd.startswith("/"):
        raise ParseError(f"subcommand 必须以 / 开头, 收到: {cmd!r}")

    subcommand = cmd[1:]  # 去掉 "/"
    if subcommand not in VALID_SUBCOMMANDS:
        raise ParseError(
            f"未知 subcommand: {subcommand!r}; 支持: {sorted(VALID_SUBCOMMANDS)}"
        )

    if window not in VALID_WINDOWS:
        raise ParseError(
            f"未知 window: {window!r}; 仅支持预设: {sorted(VALID_WINDOWS)}"
        )

    return ParsedMention(
        subcommand=subcommand,  # type: ignore[arg-type]
        window=window,           # type: ignore[arg-type]
        raw_text=text,
    )


def window_to_timedelta(window: WindowPreset, now: datetime | None = None) -> timedelta:
    """把窗口预设转换为 timedelta (相对 now 向前的时间长度).

    对 today / yesterday 需要 tz-aware now (基于其归一化为 UTC 后计算当日 0 点);
    其余 (30m/2h/7d) 忽略 now.

    返回值: 一个 timedelta, T46 用 `now - delta` 作为 since_iso 拉群消息.

    Raises:
        ValueError: now 是 tz-naive datetime; 未知 window 值.

    设计注意 (来自 T45 review):
    - tz-naive datetime 强制拒绝, 避免 subtraction TypeError (HIGH 风险)
    - 非 UTC tz-aware 归一化为 UTC 后计算, 避免负 timedelta
    - yesterday 窗口随时间增长 24h-48h (随调用时间) — 设计如此, 由 caller 评估
    """
    if window == "30m":
        return timedelta(minutes=30)
    if window == "2h":
        return timedelta(hours=2)
    if window == "7d":
        return timedelta(days=7)

    # today / yesterday 需要当前时间
    if now is None:
        now = datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must be tz-aware; got naive datetime")

    # 归一化到 UTC, 防止非 UTC 时区导致负 timedelta
    now_utc = now.astimezone(UTC)
    today_start = datetime.combine(now_utc.date(), dt_time.min, tzinfo=UTC)
    if window == "today":
        # 今天 0 点 UTC → now (≥ 0)
        return now_utc - today_start
    if window == "yesterday":
        # 昨天 0 点 UTC → now (含昨天全天 + 今天到现在)
        # 实际场景: 用户在 today 11:00 UTC 调 yesterday → 拉昨天 0 点至今 (≈ 35 小时)
        return now_utc - (today_start - timedelta(days=1))

    raise ValueError(f"未知 window: {window}")


def build_signal_from_mention(
    parsed: ParsedMention,
    chat_id: str,
    user_id: str,
    message_id: str,
) -> TriggerSignal:
    """ParsedMention + IM 上下文 → TriggerSignal (v0.4 dispatcher 入口契约)."""
    return TriggerSignal(
        type="im_mention",
        event_id=f"msg-{message_id}",
        summary=f"@TokenKnows /{parsed.subcommand} {parsed.window} · by {user_id}",
        payload={
            "command": parsed.subcommand,
            "window": parsed.window,
            "im_chat_id": chat_id,
            "triggered_by_user_id": user_id,
            "message_id": message_id,
        },
    )


# ─── 限频 (T45 / OD-3) ────────────────────────────────────


# 每用户 5min 1 次 / 每群 1h 6 次
_PER_USER_WINDOW_SEC = 300
_PER_GROUP_HOUR_SEC = 3600
_PER_GROUP_HOUR_LIMIT = 6

# 内存 fallback (Redis 不可用时); 单实例 OK
_lock = threading.Lock()
_user_last_fire: dict[tuple[str, str], float] = {}        # (chat_id, user_id) → ts
_group_recent_fires: dict[str, deque[float]] = defaultdict(deque)  # chat_id → deque[ts]


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    reason: str | None  # 拒绝原因 (用于回执 + audit)


def check_rate_limit(
    chat_id: str,
    user_id: str,
    *,
    now_ts: float | None = None,
) -> RateLimitResult:
    """同步限频检查; True=允许.

    维度 (OD-3):
    1. 同 (chat, user) 每 5 分钟最多 1 次
    2. 同 chat 全员 每 1 小时最多 6 次

    实现说明:
    - v0.5.0 用进程内 dict (单实例 OK; multi-instance 在 v0.6+ 切 Redis)
    - now_ts 参数用于单测 (freezegun 不能完全替代 time.time() 时这里手动注入)
    """
    if now_ts is None:
        now_ts = time.time()

    with _lock:
        # 1. 单用户 5min 检查 + 过期清理 (防 _user_last_fire 无界增长)
        user_key = (chat_id, user_id)
        last = _user_last_fire.get(user_key)
        if last is not None:
            if (now_ts - last) < _PER_USER_WINDOW_SEC:
                wait_sec = int(_PER_USER_WINDOW_SEC - (now_ts - last))
                return RateLimitResult(
                    allowed=False,
                    reason=f"rate_limit_per_user_5min · 还需等 {wait_sec}s",
                )
            # 过期, 主动清理避免无界增长 (T45 review HIGH 项)
            del _user_last_fire[user_key]

        # 2. 同群 1h 共 6 次检查 + 空 deque 清理 (防 chat_id 爆喷)
        group_deque = _group_recent_fires[chat_id]
        cutoff = now_ts - _PER_GROUP_HOUR_SEC
        while group_deque and group_deque[0] < cutoff:
            group_deque.popleft()
        if len(group_deque) >= _PER_GROUP_HOUR_LIMIT:
            return RateLimitResult(
                allowed=False,
                reason=f"rate_limit_per_group_hour · 本群 1h 内已触发 {len(group_deque)} 次",
            )

        # 通过: 记账; 若清理后为空且本次不通过则不必新建, 此处通过路径需要记账
        _user_last_fire[user_key] = now_ts
        group_deque.append(now_ts)
        return RateLimitResult(allowed=True, reason=None)


def _evict_empty_group_deques() -> int:
    """周期性兜底: 清理空 deque (例如 1h 后 group 无新调用)
    用于 T46 / v0.6 加调度时清理空 chat 记账; 当前可手动调.

    返回清理数量.
    """
    with _lock:
        empty_keys = [k for k, dq in _group_recent_fires.items() if not dq]
        for k in empty_keys:
            del _group_recent_fires[k]
        return len(empty_keys)


def reset_rate_limit_state() -> None:
    """仅测试用: 清空内存计数器."""
    with _lock:
        _user_last_fire.clear()
        _group_recent_fires.clear()


# ─── T46 · GroupMentionEvent 归一化 + dispatch ─────────────


_MAX_COMMAND_LEN = 200
"""命令文本上限 (来自 review LOW); /skill yesterday 16 字符, 200 是安全余量."""


_VIRTUAL_RULE_LOCK = threading.Lock()


def _ensure_virtual_mention_rule(subcommand: Subcommand):
    """幂等 upsert mention virtual rule (实例级). 让 trigger_executions.FK 有合法引用.

    3 个 subcommand 对应 3 条实例级规则; UI 列表会显示为 "@ 机器人按需 · /xxx".
    重复调用走 ON CONFLICT(id) UPDATE 路径, 不会重复插入.

    返回 TriggerRule Pydantic 对象, 供 schedule_execution 使用.
    """
    from app.persistence import get_db
    from app.schemas.auto_trigger import TriggerRule

    rule_id = f"rule-virtual-mention-{subcommand}"
    now = datetime.now(UTC)
    rule = TriggerRule(
        id=rule_id,
        project_id=None,  # 实例级 (跨项目)
        name=f"@ 机器人按需 · /{subcommand}",
        description="T46 v0.5.0 · 用户 @ 机器人触发, 不由调度器主动评估",
        mode="mention",
        asset_type=SUBCOMMAND_TO_ASSET_TYPE[subcommand],
        enabled=True,
        priority=10,
        cooldown_seconds=60,  # mention 路径不查 cooldown; schema 最小值 60
        daily_cap=100,
        created_by="system",
        created_at=now,
        updated_at=now,
    )
    with _VIRTUAL_RULE_LOCK:
        get_db().upsert_trigger_rule(
            rule_id=rule.id,
            project_id=rule.project_id,
            name=rule.name,
            mode=rule.mode,
            asset_type=rule.asset_type,
            enabled=rule.enabled,
            priority=rule.priority,
            updated_at=now.isoformat(),
            json_str=rule.model_dump_json(),
        )
    return rule


@dataclass(frozen=True)
class GroupMentionEvent:
    """从 IM 群消息事件归一化的 mention. 跨 3 家 IM 统一 (复用 v0.3 IMNormalizedMessage.mentions)."""
    platform: str             # 'feishu' / 'dingtalk' / 'wework'
    chat_id: str              # platform_chat_id
    user_id: str              # 触发者 user_id (open_id / userid)
    message_id: str           # platform_msg_id (审计 + 回执 thread parent)
    command_text: str         # 已剥离 @ 部分的 plain command (e.g. "/digest 2h")
    raw_mentions: tuple[str, ...] = ()
    """调试: 全部被 @ 的 user_id (含 bot 自己 + 其他被 @ 的人)."""


class DispatchResult:
    """dispatch_mention 结果. 由 webhook handler 转成群内回执."""

    def __init__(
        self,
        *,
        ok: bool,
        execution_id: str | None = None,
        error: str | None = None,
        reason: str | None = None,
        hint: str | None = None,
    ) -> None:
        self.ok = ok
        self.execution_id = execution_id
        self.error = error
        self.reason = reason
        self.hint = hint

    def to_log_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "execution_id": self.execution_id,
            "error": self.error, "reason": self.reason,
        }


def _strip_at_prefix(text: str) -> str:
    """剥离 IM 平台的 @ 提及前缀, 留下 plain command.

    飞书 content 通常已经是 plain text (含 "@_user_1 /digest 2h" 占位符);
    钉钉 content 是 "@TokenKnows /digest 2h" 直接含 bot 名;
    企微类似. 统一去掉首部任意 `@xxx` 段直到第一个 `/`.

    若文本不含 /, 返回 strip 后整体 (parse_command 后续报错).
    """
    if not text:
        return ""
    # 截到第一个 / (subcommand 前缀)
    idx = text.find("/")
    if idx < 0:
        return text.strip()
    return text[idx:].strip()


def normalize_im_mention(
    msg: Any,  # IMNormalizedMessage (避免循环 import 用 Any)
    bot_user_id: str | None,
) -> GroupMentionEvent | None:
    """从 IMNormalizedMessage 提取 mention 命令.

    返回 None 表示不是 mention 触发 (msg 不含 bot mention / bot_user_id 未配置).

    Args:
        msg: v0.3 已归一化的消息 (有 mentions list[str])
        bot_user_id: 当前平台 bot 的 user_id (settings.feishu_bot_open_id 等)
                     None / 空串 → 静默跳过 (fail-soft, 防 env 未配置时崩溃)
    """
    if not bot_user_id:
        return None
    if not getattr(msg, "mentions", None):
        return None
    if bot_user_id not in msg.mentions:
        return None
    # 抽 sender
    sender = getattr(msg, "sender", None)
    if sender is None or not getattr(sender, "user_id", None):
        return None  # 无 sender 不能限频 + 审计

    content = getattr(msg, "content", "") or ""
    if len(content) > _MAX_COMMAND_LEN:
        # 命令过长直接拒, 后续 parse 也会拒
        content = content[:_MAX_COMMAND_LEN]

    command_text = _strip_at_prefix(content)

    return GroupMentionEvent(
        platform=getattr(msg, "platform", "unknown"),
        chat_id=msg.platform_chat_id,
        user_id=sender.user_id,
        message_id=msg.platform_msg_id,
        command_text=command_text,
        raw_mentions=tuple(msg.mentions),
    )


def resolve_project_for_chat(connection_id: str) -> str | None:
    """im_connection 反查 project_id (v0.3 schema 保证 NOT NULL).

    传入 connection.id (由 webhook handler 已 resolve);
    返回该 connection 绑定的 project_id, 不存在返 None.
    """
    # 延迟 import 避免循环
    from app.persistence import get_db

    raw = get_db().get_im_connection(connection_id)
    if raw is None:
        return None
    return raw.get("project_id")


def dispatch_mention(
    event: GroupMentionEvent,
    connection_id: str,
) -> DispatchResult:
    """主流程: parse → rate_limit → schedule_execution.

    1. 解析命令 (ParseError → 返回 hint 帮助文本)
    2. 限频检查 (RateLimitResult 拒绝 → 返回 reason)
    3. resolve project_id (未绑定 → 错误)
    4. 构造 TriggerSignal + 调 svc.schedule_execution (withdraw_window_min=0 立即 fire)

    返回 DispatchResult 供 webhook handler 转群内回执.
    不抛异常给 caller (webhook 必须 200, 错误转回执即可).
    """
    from app.config.logging import logger

    # 1. parse
    try:
        parsed = parse_command(event.command_text)
    except ParseError as e:
        logger.info(
            "mention_parse_error",
            chat=event.chat_id, user=event.user_id, error=str(e),
            raw=event.command_text[:200],
        )
        return DispatchResult(
            ok=False, error="parse_error", reason=str(e),
            hint="命令格式: @TokenKnows /<distill|digest|skill> <30m|2h|today|yesterday|7d>",
        )

    # 2. rate limit
    rl = check_rate_limit(event.chat_id, event.user_id)
    if not rl.allowed:
        logger.warning(
            "mention_rate_limited",
            chat=event.chat_id, user=event.user_id, reason=rl.reason,
        )
        return DispatchResult(
            ok=False, error="rate_limited", reason=rl.reason,
            hint="过段时间再试 (单用户 5min 1 次 / 同群 1h 6 次)",
        )

    # 3. resolve project
    project_id = resolve_project_for_chat(connection_id)
    if project_id is None:
        logger.warning("mention_no_project", connection_id=connection_id)
        return DispatchResult(
            ok=False, error="no_project",
            reason="本群未绑定 TokenKnows 项目",
            hint="请联系管理员在 TokenKnows 项目设置中绑定本 IM 连接",
        )

    # 4. 构造 signal + schedule
    signal = build_signal_from_mention(
        parsed, event.chat_id, event.user_id, event.message_id,
    )

    # 复用 v0.4 dispatcher 完整管线; mention 用 "virtual rule" 概念:
    # - 实例级 (project_id=None), 3 个固定 id (一个 subcommand 一个)
    # - 幂等 upsert (DB 主键冲突自动 update_at 刷新)
    # - 让 trigger_executions 的 FK 有合法引用 + 审计能在 UI 看到 "mention 规则"
    virtual_rule = _ensure_virtual_mention_rule(parsed.subcommand)
    from app.services import auto_trigger_service as svc

    try:
        execution = svc.schedule_execution(
            virtual_rule, project_id, signal,
            withdraw_window_min=0,  # 立即 fire (用户主动触发, 撤回无意义; OD-5)
        )
    except Exception as e:
        from app.config.logging import logger
        logger.error(
            "mention_schedule_failed",
            chat=event.chat_id, user=event.user_id, error=str(e),
        )
        return DispatchResult(
            ok=False, error="schedule_failed", reason=str(e),
            hint="系统错误, 请稍后再试",
        )

    from app.config.logging import logger
    logger.info(
        "mention_dispatched",
        chat=event.chat_id, user=event.user_id,
        subcommand=parsed.subcommand, window=parsed.window,
        project_id=project_id, execution_id=execution.id,
    )

    # T47 · 群内 thread 回执 (Proposal OD-5).
    # 失败仅 log 不抛 (reply 是次要 UX, asset 已 schedule, 不能阻塞主路径).
    try:
        from app.persistence import get_db
        from app.services.im.thread_reply import build_reply_text, reply_in_thread

        connection_raw = get_db().get_im_connection(connection_id)
        if connection_raw is not None:
            reply_text = build_reply_text(
                subcommand=parsed.subcommand,
                window=parsed.window,
                execution_id=execution.id,
                project_id=project_id,
                user_id=event.user_id,
            )
            reply_in_thread(
                connection_raw=connection_raw,
                chat_id=event.chat_id,
                parent_message_id=event.message_id,
                text=reply_text,
            )
    except Exception as e:
        logger.warning(
            "mention_thread_reply_hook_failed",
            execution_id=execution.id, error=str(e),
        )

    return DispatchResult(
        ok=True, execution_id=execution.id,
        reason=f"scheduled · {parsed.subcommand}/{parsed.window}",
    )


__all__ = [
    "Subcommand",
    "WindowPreset",
    "ParsedMention",
    "ParseError",
    "RateLimitResult",
    "GroupMentionEvent",
    "DispatchResult",
    "VALID_SUBCOMMANDS",
    "VALID_WINDOWS",
    "SUBCOMMAND_TO_ASSET_TYPE",
    "parse_command",
    "window_to_timedelta",
    "build_signal_from_mention",
    "check_rate_limit",
    "normalize_im_mention",
    "resolve_project_for_chat",
    "dispatch_mention",
    # 不导出 reset_rate_limit_state / _evict_empty_group_deques (内部 + test-only,
    # 但测试可显式 import; 避免 from module import * 暴露状态修改钩子)
]
