"""IM REST API (v0.3 T23).

来源: Proposal §10 + engineering_handoff/tasks/T23-im-rest-api.md

11 个端点:
- 连接: POST/GET list/GET detail/PATCH status/DELETE
- 群: GET list/POST join/POST leave/GET stats
- 消息: GET list (默认不返 content)
- 蒸馏: POST distill (按需触发 ValueSegment → Skill)
"""

from __future__ import annotations

from typing import Literal

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config.logging import logger
from app.config.settings import get_settings
from app.persistence import get_db
from app.schemas.im import (
    IMConnection,
    IMConnectionStatus,
    IMPlatform,
    IMSourceMode,
    ValueSegment,
)
from app.services import im_service
from app.services.im import retention
from app.services.im.connector_base import (
    ConnectorError,
    TokenExpiredError,
)
from app.services.im import distill_jobs
from app.services.im.distill_jobs import DistillJob, JobStatus
from app.services.im.value_segment_service import (
    process_messages_to_segments,
)

router = APIRouter()


# ─── DTO ─────────────────────────────────────────────────────


class CreateConnectionRequest(BaseModel):
    platform: IMPlatform
    consent_signed_by: str | None = None
    consent_user_id: str | None = None


class CreateConnectionResponse(BaseModel):
    connection: IMConnection
    authorize_url: str


class UpdateConnectionRequest(BaseModel):
    status: IMConnectionStatus | None = None
    """暂停/恢复使用 active/revoked."""


class JoinChatResponse(BaseModel):
    ok: bool
    note: str | None = None


class ChatStats(BaseModel):
    chat_id: str
    message_count: int
    signal_count: int
    signal_rate: float
    top_contributors: list[dict]


class DistillRequest(BaseModel):
    chat_id: str
    source_mode: IMSourceMode = "assistant"


class DistillResponse(BaseModel):
    segments_persisted: int
    segment_ids: list[str]


class SignalConfig(BaseModel):
    threshold: float = Field(ge=0.0, le=1.0)
    llm_model: str | None = None


class SignalConfigUpdate(BaseModel):
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    llm_model: str | None = None


# ─── 连接 CRUD ───────────────────────────────────────────────


@router.post(
    "/projects/{project_id}/im/connections",
    response_model=CreateConnectionResponse,
    status_code=201,
)
async def create_connection(
    project_id: str, body: CreateConnectionRequest
) -> CreateConnectionResponse:
    """新建 IM connection 并返回 authorize_url. 用户打开 URL 完成 OAuth 后,
    跳回 /webhooks/feishu/auth-callback 完成激活.
    """
    conn = im_service.create_connection(
        project_id=project_id,
        platform=body.platform,
        consent_signed_by=body.consent_signed_by,
        consent_user_id=body.consent_user_id,
    )
    instance = im_service.build_connector(conn)
    settings = get_settings()
    redirect_uri = settings.feishu_oauth_redirect_uri  # MVP 仅飞书一套
    try:
        url = await instance.get_authorize_url(
            project_id=project_id,
            redirect_uri=redirect_uri,
            state=conn.id,
        )
    except ConnectorError as e:
        # 凭据未配置 → 给假 URL 让前端提示用户去 .env 配
        logger.warning("im_authorize_url_failed", error=str(e))
        url = f"#im-not-configured:{e}"
    return CreateConnectionResponse(connection=conn, authorize_url=url)


@router.get(
    "/projects/{project_id}/im/connections",
    response_model=list[IMConnection],
)
async def list_connections(
    project_id: str,
    status: IMConnectionStatus | None = None,
) -> list[IMConnection]:
    return im_service.list_connections(project_id, status)


@router.get("/im/connections/{connection_id}", response_model=IMConnection)
async def get_connection(connection_id: str) -> IMConnection:
    conn = im_service.get_connection(connection_id)
    if conn is None:
        raise HTTPException(404, detail="Connection not found")
    return conn


@router.patch("/im/connections/{connection_id}", response_model=IMConnection)
async def update_connection(
    connection_id: str, body: UpdateConnectionRequest
) -> IMConnection:
    if body.status is None:
        raise HTTPException(400, detail="status 字段必填")
    updated = im_service.update_status(connection_id, body.status)
    if updated is None:
        raise HTTPException(404, detail="Connection not found")
    return updated


@router.delete("/im/connections/{connection_id}", status_code=204)
async def revoke_connection(connection_id: str) -> None:
    """撤回 (DELETE 语义 = 用户撤回授权, 不是物理删除).

    标 status=revoked + 启动 30 天宽限期; 真删由 T22 retention_sweep 处理.
    """
    revoked = retention.revoke_connection(connection_id)
    if revoked is None:
        raise HTTPException(404, detail="Connection not found")
    return None


# ─── 群 ──────────────────────────────────────────────────────


@router.get("/im/connections/{connection_id}/chats")
async def list_chats(connection_id: str) -> list[dict]:
    conn = im_service.get_connection(connection_id)
    if conn is None:
        raise HTTPException(404, detail="Connection not found")
    instance = im_service.build_connector(conn)
    try:
        return await instance.list_chats()
    except TokenExpiredError as e:
        raise HTTPException(401, detail=f"access_token 已过期, 需重连: {e}") from e
    except ConnectorError as e:
        raise HTTPException(502, detail=str(e)) from e


@router.post(
    "/im/connections/{connection_id}/chats/{chat_id}/join",
    response_model=JoinChatResponse,
)
async def join_chat(connection_id: str, chat_id: str) -> JoinChatResponse:
    conn = im_service.get_connection(connection_id)
    if conn is None:
        raise HTTPException(404, detail="Connection not found")
    instance = im_service.build_connector(conn)
    try:
        await instance.add_bot_to_chat(chat_id)
    except TokenExpiredError as e:
        raise HTTPException(401, detail=str(e)) from e
    except ConnectorError as e:
        raise HTTPException(502, detail=str(e)) from e
    return JoinChatResponse(ok=True)


@router.post(
    "/im/connections/{connection_id}/chats/{chat_id}/leave",
    response_model=JoinChatResponse,
)
async def leave_chat(connection_id: str, chat_id: str) -> JoinChatResponse:
    """踢 bot. MVP 暂未实施 platform leave API → 仅返回 ok."""
    conn = im_service.get_connection(connection_id)
    if conn is None:
        raise HTTPException(404, detail="Connection not found")
    return JoinChatResponse(ok=True, note="MVP 暂未实施 platform leave; 仅本地标记")


@router.get(
    "/im/connections/{connection_id}/chats/{chat_id}/stats",
    response_model=ChatStats,
)
async def chat_stats(connection_id: str, chat_id: str) -> ChatStats:
    """单 chat 的统计: 消息数 / signal 数 / 比率 / TOP contributors."""
    conn = im_service.get_connection(connection_id)
    if conn is None:
        raise HTTPException(404, detail="Connection not found")
    db = get_db()
    msgs = db.list_im_messages(connection_id, chat_id=chat_id, limit=5000)
    total = len(msgs)
    signal_cnt = sum(1 for m in msgs if m.get("is_signal"))
    rate = signal_cnt / total if total else 0.0
    # top contributors
    contributor_counts: dict[str, dict] = {}
    for m in msgs:
        sender = m.get("sender") or {}
        sid = sender.get("user_id")
        if not sid:
            continue
        entry = contributor_counts.setdefault(
            sid, {"user_id": sid, "name": sender.get("name"), "messages": 0}
        )
        entry["messages"] += 1
    top = sorted(
        contributor_counts.values(), key=lambda x: x["messages"], reverse=True
    )[:5]
    return ChatStats(
        chat_id=chat_id,
        message_count=total,
        signal_count=signal_cnt,
        signal_rate=round(rate, 3),
        top_contributors=top,
    )


# ─── 消息 ────────────────────────────────────────────────────


@router.get(
    "/im/connections/{connection_id}/messages",
)
async def list_messages(
    connection_id: str,
    chat_id: str | None = Query(default=None),
    include_content: bool = Query(default=False, description="默认不返 content 保护隐私"),
    signal_only: bool = Query(default=False),
    limit: int = Query(default=100, le=500),
) -> list[dict]:
    conn = im_service.get_connection(connection_id)
    if conn is None:
        raise HTTPException(404, detail="Connection not found")
    rows = get_db().list_im_messages(
        connection_id, chat_id=chat_id, signal_only=signal_only, limit=limit
    )
    if not include_content:
        for r in rows:
            r["content"] = None
    return rows


# ─── 蒸馏触发 ────────────────────────────────────────────────


@router.post(
    "/im/connections/{connection_id}/distill",
    response_model=DistillResponse,
)
async def trigger_distill(
    connection_id: str, body: DistillRequest
) -> DistillResponse:
    """从指定 chat 的消息触发 ValueSegment 组装 + 入库 (不调下游 Skill)."""
    conn = im_service.get_connection(connection_id)
    if conn is None:
        raise HTTPException(404, detail="Connection not found")
    # 拉该 chat 全部消息, 转 IMNormalizedMessage
    db = get_db()
    rows = db.list_im_messages(connection_id, chat_id=body.chat_id, limit=2000)
    if not rows:
        return DistillResponse(segments_persisted=0, segment_ids=[])
    from datetime import datetime
    from app.schemas.im import IMUser
    from app.services.im.connector_base import IMNormalizedMessage
    msgs: list[IMNormalizedMessage] = []
    for r in rows:
        sender_data = r.get("sender") or {}
        sender = IMUser(
            user_id=sender_data.get("user_id", ""),
            name=sender_data.get("name"),
        )
        msgs.append(IMNormalizedMessage(
            platform=conn.platform,
            platform_chat_id=r["platform_chat_id"],
            platform_msg_id=r["platform_msg_id"],
            sender=sender,
            content=r.get("content") or "",
            mentions=r.get("mentions") or [],
            received_at=datetime.fromisoformat(r["received_at"]),
            raw_event_type="message",
        ))
    # received_at 升序
    msgs.sort(key=lambda m: m.received_at)
    persisted = process_messages_to_segments(
        conn.project_id, msgs, source_mode=body.source_mode
    )
    logger.info(
        "im_distill_done",
        connection=connection_id,
        chat=body.chat_id,
        segments=len(persisted),
    )
    return DistillResponse(
        segments_persisted=len(persisted),
        segment_ids=[s.id for s in persisted],
    )


# ─── v0.3.1 G · SignalGate 阈值 + 模型 ─────────────────────


@router.get(
    "/projects/{project_id}/im/signal/config",
    response_model=SignalConfig,
)
async def get_signal_config(project_id: str) -> SignalConfig:
    """读 SignalGate 当前配置 (MVP 实例级; project 隔离留 v0.4)."""
    s = get_settings()
    return SignalConfig(
        threshold=s.signal_gate_threshold,
        llm_model=s.signal_gate_llm_model or None,
    )


# ─── v0.3.1 H · Distill 异步 + SSE ────────────────────────


class DistillJobInfo(BaseModel):
    job_id: str
    connection_id: str
    chat_id: str
    status: str
    messages_total: int
    messages_processed: int
    segments_persisted: int
    segment_ids: list[str]
    error: str | None = None


def _job_to_info(job: DistillJob) -> DistillJobInfo:
    return DistillJobInfo(
        job_id=job.job_id,
        connection_id=job.connection_id,
        chat_id=job.chat_id,
        status=job.status.value,
        messages_total=job.messages_total,
        messages_processed=job.messages_processed,
        segments_persisted=job.segments_persisted,
        segment_ids=job.segment_ids,
        error=job.error,
    )


@router.post(
    "/im/connections/{connection_id}/distill-async",
    response_model=DistillJobInfo,
    status_code=202,
)
async def trigger_distill_async(
    connection_id: str, body: DistillRequest
) -> DistillJobInfo:
    """异步触发蒸馏. 立即返 job_id; 前端订阅 /distill-jobs/{id}/stream 看进度."""
    conn = im_service.get_connection(connection_id)
    if conn is None:
        raise HTTPException(404, detail="Connection not found")
    job = distill_jobs.start_distill_job(
        project_id=conn.project_id,
        connection_id=connection_id,
        chat_id=body.chat_id,
        source_mode=body.source_mode,
    )
    return _job_to_info(job)


@router.get(
    "/im/distill-jobs/{job_id}",
    response_model=DistillJobInfo,
)
async def get_distill_job(job_id: str) -> DistillJobInfo:
    job = distill_jobs.get_registry().get(job_id)
    if job is None:
        raise HTTPException(404, detail="Job not found")
    return _job_to_info(job)


@router.get("/im/distill-jobs/{job_id}/stream")
async def stream_distill_job(job_id: str) -> StreamingResponse:
    """SSE 实时推送 distill 进度.

    事件:
      data: {"event": "started", ...}
      data: {"event": "progress", "stage": "...", ...}
      data: {"event": "completed", "segments_persisted": N, "segment_ids": [...]}
      data: {"event": "failed", "error": "..."}
    """
    registry = distill_jobs.get_registry()
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(404, detail="Job not found")

    async def generate():
        q = registry.subscribe(job_id)
        # 1. 推送当前快照 (前端 join 慢时也能立刻看状态)
        snapshot = _job_to_info(registry.get(job_id) or job)
        yield f"event: snapshot\ndata: {snapshot.model_dump_json()}\n\n"
        try:
            while True:
                # 终态后跳出
                cur = registry.get(job_id)
                if cur and cur.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                    # 把剩余事件 drain 后退出
                    try:
                        ev = q.get_nowait()
                        yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                        continue
                    except asyncio.QueueEmpty:
                        break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            registry.unsubscribe(job_id, q)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.patch(
    "/projects/{project_id}/im/signal/config",
    response_model=SignalConfig,
)
async def patch_signal_config(
    project_id: str, body: SignalConfigUpdate
) -> SignalConfig:
    """运行时调阈值 / 切 LLM 模型 (持久化到 settings 实例; 重启失效).

    生产应该持久化到 project.im_settings; 留 v0.4.
    """
    s = get_settings()
    if body.threshold is not None:
        s.signal_gate_threshold = body.threshold
    if body.llm_model is not None:
        s.signal_gate_llm_model = body.llm_model
    return SignalConfig(
        threshold=s.signal_gate_threshold,
        llm_model=s.signal_gate_llm_model or None,
    )
