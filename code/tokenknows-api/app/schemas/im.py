"""IM 集成 DTO · v0.3 起步 (T16).

来源:
- Proposal_IM_KnowledgeDistillation_v0.3.md §8 数据模型
- engineering_handoff/tasks/T16-im-db-schema.md

设计偏差 (MVP SQLite vs Proposal PG):
- 不做 pg_partman 分区 (SQLite 不支持); retention_until 索引扫即可
- auth_token / refresh_token 用 Fernet 加密后存 hex 字符串 (而非 BYTEA)
- im_chat 概念不单独建表, 用 im_messages.platform_chat_id 字段; T19 接 provider
  时如需可再建 chat 表
- im_consent 信息内嵌到 im_connections (consent_signed_by + consent_signed_at);
  撤销 = status=revoked + revoked_at 时间戳
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ─── 类型定义 ────────────────────────────────────────────────

IMPlatform = Literal["feishu", "dingtalk", "wework", "email"]
"""支持的 IM 平台. 个人微信不接 (官方协议封禁风险, 详见 Proposal §3.2)."""

IMConnectionStatus = Literal[
    "pending",   # 待企业管理员确认 OR 待员工授权
    "active",    # 双签完成, 可拉消息
    "revoked",   # 用户主动撤销或 token 失效
]

IMSourceMode = Literal[
    "assistant",  # 模式 A · 个人助理: 私聊机器人, 不存原文
    "archive",    # 模式 B · 会话存档: 部分群已授权, 存原文 (90 天)
]

ValueSegmentSourceType = Literal[
    "event",      # 现有 events 表 (MVP 已实施)
    "im_chat",    # v0.3 · 单条 IM 消息蒸馏
    "im_thread",  # v0.3 · IM 多条上下文 (会话片段) 蒸馏
]


# ─── 嵌入对象 ────────────────────────────────────────────────


class IMUser(BaseModel):
    """IM 消息发送者 / 提及对象."""

    user_id: str
    """平台内部 user_id (open_id / userid)."""

    name: str | None = None
    """显示名 (有则填, 拉不到留空)."""

    email: str | None = None


class ValueSegmentSource(BaseModel):
    """ValueSegment 的来源追溯."""

    type: ValueSegmentSourceType

    mode: IMSourceMode | None = None
    """仅当 type 是 im_chat / im_thread 时填."""

    im_chat_id: str | None = None
    """平台会话 id (im_messages.platform_chat_id)."""

    im_message_ids: list[str] = Field(default_factory=list)
    """蒸馏所用的 IM 消息 ID 列表 (im_messages.id)."""

    event_id: str | None = None
    """type=event 时填."""

    contributors: list[IMUser] = Field(default_factory=list)
    """参与者列表 (用于价值归因 / 引用)."""


# ─── 主表 ────────────────────────────────────────────────────


class IMConnection(BaseModel):
    """单条 IM 接入授权 (双签后激活).

    auth_token_enc / refresh_token_enc 存 Fernet 加密后的 utf-8 hex.
    通过 app.services.im_crypto.encrypt_token / decrypt_token 透明加解密.
    """

    id: str
    project_id: str
    platform: IMPlatform
    tenant_name: str | None = None
    """企业域 (e.g. tenant_key / corp_id) 显示名."""

    auth_token_enc: str | None = None
    """加密后的 access_token (Fernet ciphertext hex)."""

    refresh_token_enc: str | None = None
    """加密后的 refresh_token (Fernet ciphertext hex)."""

    token_expires_at: datetime | None = None

    consent_signed_by: str | None = None
    """企业管理员的 user_id (双签授权第一签)."""

    consent_user_id: str | None = None
    """员工的 user_id (双签授权第二签)."""

    consent_signed_at: datetime | None = None
    """双签完成时刻; status=active 才有值."""

    revoked_at: datetime | None = None

    status: IMConnectionStatus = "pending"
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class IMMessage(BaseModel):
    """单条 IM 消息 (原文); UNIQUE (connection_id, platform_msg_id) 保幂等.

    保留期: 默认 90 天 (Proposal §6.4); retention_until 由 sync 时计算.
    """

    id: str
    connection_id: str
    platform_chat_id: str
    """会话 id (group / DM / email thread)."""

    platform_msg_id: str
    """原始消息 id (e.g. message_id / mid)."""

    sender: IMUser | None = None
    content: str
    """原文 markdown / text; 不含敏感数据 (敏感由 T22 redaction 处理)."""

    mentions: list[str] = Field(default_factory=list)
    """被 @ 的 user_id 列表 (T20 SignalGate 用)."""

    is_signal: bool = False
    """T20 SignalGate 判定是否"信号消息"(含 @, 决策语, 行动项)."""

    received_at: datetime

    retention_until: datetime | None = None
    """自动清理时刻 (默认 received_at + 90 天)."""

    redacted: bool = False
    """已经 T22 脱敏处理过."""


class ValueSegment(BaseModel):
    """脱敏 + 价值提炼后可出域的文本片段.

    跨 source_type 共享同一抽象;
    - source.type = event → 与 MVP 现有流水线兼容
    - source.type = im_* → v0.3 IM 蒸馏专属 (mode 必填)
    """

    id: str
    project_id: str
    source: ValueSegmentSource
    content: str
    """脱敏后的可出域文本 (经 T22 处理)."""

    trust_score: float = Field(default=0.5, ge=0.0, le=1.0)
    extracted_at: datetime
