"""IM 数据保留期 + 撤回流程 (v0.3 T22).

来源:
- engineering_handoff/tasks/T22-retention-revocation.md
- Proposal §11.5 + §12 R10

设计:
- 默认 90 天: im_messages.retention_until = received_at + 90 天
- 定时清理: expire_messages() 找到 retention_until <= now 且 redacted=0 的消息,
            T22 标 redacted=1 + content 替换为占位符 (不删派生 ValueSegment)
- 撤回流程: revoke_connection() 立刻标 status=revoked, 调度 30 天后强制清理
- 同意撤回: anonymize_user_segments() 把 ValueSegment.contributors 中的用户标匿名

MVP 简化:
- 不依赖 APScheduler / Celery; 暴露 expire_messages_now() 函数, main 启动 asyncio
  后台 task 每小时调一次. 生产换专门 worker.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.config.logging import logger
from app.persistence import get_db
from app.schemas.im import IMConnection, ValueSegment
from app.services import im_service

DEFAULT_RETENTION_DAYS = 90
"""消息原文保留天数."""

REVOCATION_GRACE_DAYS = 30
"""撤回后强制清理的宽限期."""

REDACTED_PLACEHOLDER = "[message retention expired]"
"""到期消息的占位 content."""

EXPIRE_BATCH_SIZE = 500
"""单次扫描最多处理多少消息."""


def compute_retention_until(
    received_at: datetime, retention_days: int = DEFAULT_RETENTION_DAYS
) -> datetime:
    """计算消息的保留截止时间."""
    return received_at + timedelta(days=retention_days)


# ─── 到期清理 ────────────────────────────────────────────────


def expire_messages_now(now: datetime | None = None) -> dict:
    """主清理逻辑. 扫到期消息, 替换 content + 标 redacted=1.

    Returns:
        {"scanned": int, "redacted": int, "errors": int}
    """
    cutoff = (now or datetime.now(UTC)).isoformat()
    db = get_db()
    ids = db.expire_im_messages(cutoff)
    if not ids:
        return {"scanned": 0, "redacted": 0, "errors": 0}

    redacted_count = 0
    errors = 0
    for msg_id in ids[:EXPIRE_BATCH_SIZE]:
        try:
            raw = _load_message_dict(db, msg_id)
            if raw is None:
                errors += 1
                continue
            anonymized = _redact_message_dict(raw)
            db.mark_im_message_redacted(msg_id, anonymized)
            redacted_count += 1
        except Exception as e:
            logger.warning("im_retention_redact_failed", id=msg_id, error=str(e))
            errors += 1

    logger.info(
        "im_retention_swept",
        scanned=len(ids),
        redacted=redacted_count,
        errors=errors,
    )
    return {"scanned": len(ids), "redacted": redacted_count, "errors": errors}


def _load_message_dict(db, message_id: str) -> dict | None:
    """直接从 SQLite 拉 im_messages.json (无专用 get_im_message; 走 list with filter)."""
    rows = db._query(
        "SELECT json FROM im_messages WHERE id = ?", (message_id,)
    )
    if not rows:
        return None
    import json
    return json.loads(rows[0]["json"])


def _redact_message_dict(raw: dict) -> str:
    """脱敏单条消息. 把 content 改为占位符, 保留元数据 (id/sender/timestamp).

    返回 model_dump_json() 兼容字符串.
    """
    import json
    raw = dict(raw)  # shallow copy 避免改 cache
    raw["content"] = REDACTED_PLACEHOLDER
    raw["redacted"] = True
    return json.dumps(raw, ensure_ascii=False)


# ─── 撤回流程 ────────────────────────────────────────────────


def revoke_connection(connection_id: str) -> IMConnection | None:
    """立刻标 status=revoked + 写 revoked_at. 真正消息清理由 schedule 调.

    Returns:
        更新后的 IMConnection, 不存在返 None
    """
    updated = im_service.update_status(connection_id, "revoked")
    if updated is None:
        return None
    logger.info(
        "im_connection_revoked",
        id=connection_id,
        grace_until=(datetime.now(UTC) + timedelta(days=REVOCATION_GRACE_DAYS)).isoformat(),
    )
    return updated


def force_purge_revoked_connection(
    connection_id: str, now: datetime | None = None
) -> dict:
    """撤回宽限期到 (默认 30 天) 后强制清理所有消息.

    Returns:
        {"messages_redacted": int, "messages_total": int}
    """
    db = get_db()
    conn_data = db.get_im_connection(connection_id)
    if conn_data is None:
        return {"messages_redacted": 0, "messages_total": 0}
    conn = IMConnection.model_validate(conn_data)
    if conn.status != "revoked":
        logger.warning(
            "im_force_purge_skipped_not_revoked",
            id=connection_id, status=conn.status,
        )
        return {"messages_redacted": 0, "messages_total": 0}
    now_dt = now or datetime.now(UTC)
    if conn.revoked_at is None or (now_dt - conn.revoked_at) < timedelta(
        days=REVOCATION_GRACE_DAYS
    ):
        logger.info(
            "im_force_purge_within_grace",
            id=connection_id,
            grace_remaining_days=REVOCATION_GRACE_DAYS,
        )
        return {"messages_redacted": 0, "messages_total": 0}
    # 所有该 connection 的消息标 redacted
    msgs = db.list_im_messages(connection_id, limit=10000)
    redacted = 0
    for m in msgs:
        if m.get("redacted"):
            continue
        try:
            anon = _redact_message_dict(m)
            db.mark_im_message_redacted(m["id"], anon)
            redacted += 1
        except Exception as e:
            logger.warning(
                "im_force_purge_redact_failed", id=m.get("id"), error=str(e)
            )
    logger.info(
        "im_force_purge_done", id=connection_id,
        messages_redacted=redacted, total=len(msgs),
    )
    return {"messages_redacted": redacted, "messages_total": len(msgs)}


# ─── 同意撤回 / 个人匿名化 ───────────────────────────────────


def anonymize_user_segments(project_id: str, user_id: str) -> int:
    """某用户撤回个人同意 → 把其在 ValueSegment.contributors 中的标匿名.

    实施: 把 contributors[].name → "anonymous", user_id → "anon-<hash 前 6>".
    保留 ValueSegment 派生数据 (合规要求: 已蒸馏不可逆), 但用户身份不再可关联.

    Returns:
        受影响的 ValueSegment 数
    """
    import hashlib
    db = get_db()
    segments = db.list_value_segments(project_id, limit=10000)
    pseudo_id = "anon-" + hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:6]
    affected = 0
    for s in segments:
        source = s.get("source") or {}
        contributors = source.get("contributors") or []
        modified = False
        for c in contributors:
            if c.get("user_id") == user_id:
                c["user_id"] = pseudo_id
                c["name"] = "anonymous"
                c["email"] = None
                modified = True
        if modified:
            try:
                import json
                vs = ValueSegment.model_validate(s)
                db.upsert_value_segment(
                    segment_id=vs.id,
                    project_id=project_id,
                    source_type=vs.source.type,
                    trust_score=vs.trust_score,
                    extracted_at=vs.extracted_at.isoformat(),
                    json_str=json.dumps(s, ensure_ascii=False),
                )
                affected += 1
            except Exception as e:
                logger.warning(
                    "im_anonymize_segment_failed",
                    segment_id=s.get("id"), error=str(e),
                )
    logger.info(
        "im_user_anonymized",
        project=project_id, user_id=user_id, affected=affected,
    )
    return affected


# ─── 到期前通知 (T22 stub) ───────────────────────────────────


def upcoming_expirations(
    days_ahead: int = 7, now: datetime | None = None
) -> list[dict]:
    """找未来 N 天内将到期的消息. MVP 仅返回数据, 不发送通知.

    Returns:
        [{"connection_id", "count", "earliest_until"}, ...]
    """
    base = now or datetime.now(UTC)
    cutoff = (base + timedelta(days=days_ahead)).isoformat()
    db = get_db()
    rows = db._query(
        """
        SELECT connection_id, COUNT(*) AS n, MIN(retention_until) AS earliest
        FROM im_messages
        WHERE retention_until IS NOT NULL
          AND retention_until <= ?
          AND retention_until > ?
          AND redacted = 0
        GROUP BY connection_id
        """,
        (cutoff, base.isoformat()),
    )
    return [
        {
            "connection_id": r["connection_id"],
            "count": r["n"],
            "earliest_until": r["earliest"],
        }
        for r in rows
    ]


# ─── 后台 task 调度 ──────────────────────────────────────────


async def retention_sweep_loop(interval_seconds: int = 3600) -> None:
    """每 N 秒跑一次 expire_messages_now. 调用方 (main lifespan) 用
    asyncio.create_task() 启动."""
    while True:
        try:
            expire_messages_now()
        except Exception as e:
            logger.error("im_retention_sweep_failed", error=str(e))
        await asyncio.sleep(interval_seconds)
