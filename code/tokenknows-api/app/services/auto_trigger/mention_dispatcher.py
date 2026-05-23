"""@ 机器人按需触发 · v0.5.0 (T45-T47).

本文件 v0.5.0 分 3 个 task 渐进填充:
- T45 (本提交): 命令解析 + 限频 + Schema helper (纯函数, 无 IO)
- T46: IM webhook 接入 + dispatch_mention 主流程
- T47: 群内 thread 回执

设计依据:
- Proposal_OnDemand_and_ContributorConsent_v0.5.md §2.1-2.3 (OD-1/OD-3/OD-4)
- engineering_handoff/tasks/T45-mention-command-parser.md
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Literal

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

    对 today / yesterday 需要传 now (基于其计算当日 0 点); 其余忽略 now.

    返回值: 一个 timedelta, T46 用 `now - delta` 作为 since_iso 拉群消息.
    """
    if window == "30m":
        return timedelta(minutes=30)
    if window == "2h":
        return timedelta(hours=2)
    if window == "7d":
        return timedelta(days=7)

    # today / yesterday 需要当前时间
    if now is None:
        now = datetime.now(timezone.utc)

    # 简化: 用 UTC; v0.5.1 加项目级时区配置 (Proposal §6.1)
    today_start = datetime.combine(now.date(), dt_time.min, tzinfo=timezone.utc)
    if window == "today":
        # 今天 0 点 → now
        return now - today_start
    if window == "yesterday":
        # 昨天 0 点 → now (含昨天全天 + 今天到现在)
        # 实际场景: 用户在 today 11:00 调 yesterday → 拉昨天 0 点至今 (≈ 35 小时)
        return now - (today_start - timedelta(days=1))

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
        # 1. 单用户 5min 检查
        user_key = (chat_id, user_id)
        last = _user_last_fire.get(user_key)
        if last is not None and (now_ts - last) < _PER_USER_WINDOW_SEC:
            wait_sec = int(_PER_USER_WINDOW_SEC - (now_ts - last))
            return RateLimitResult(
                allowed=False,
                reason=f"rate_limit_per_user_5min · 还需等 {wait_sec}s",
            )

        # 2. 同群 1h 共 6 次检查
        group_deque = _group_recent_fires[chat_id]
        # 清理过期 (> 1h 之前的)
        cutoff = now_ts - _PER_GROUP_HOUR_SEC
        while group_deque and group_deque[0] < cutoff:
            group_deque.popleft()
        if len(group_deque) >= _PER_GROUP_HOUR_LIMIT:
            oldest_age = int(now_ts - group_deque[0])
            return RateLimitResult(
                allowed=False,
                reason=f"rate_limit_per_group_hour · 本群 1h 内已触发 {len(group_deque)} 次",
            )

        # 通过: 记账
        _user_last_fire[user_key] = now_ts
        group_deque.append(now_ts)
        return RateLimitResult(allowed=True, reason=None)


def reset_rate_limit_state() -> None:
    """仅测试用: 清空内存计数器."""
    with _lock:
        _user_last_fire.clear()
        _group_recent_fires.clear()


__all__ = [
    "Subcommand",
    "WindowPreset",
    "ParsedMention",
    "ParseError",
    "RateLimitResult",
    "VALID_SUBCOMMANDS",
    "VALID_WINDOWS",
    "SUBCOMMAND_TO_ASSET_TYPE",
    "parse_command",
    "window_to_timedelta",
    "build_signal_from_mention",
    "check_rate_limit",
    "reset_rate_limit_state",
]
