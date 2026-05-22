"""IMConnector ABC + IMNormalizedMessage + ConnectorRegistry (v0.3 T17).

来源:
- engineering_handoff/tasks/T17-im-connector-abstract.md
- Proposal_IM_KnowledgeDistillation_v0.3.md §9.2

设计要点:
- 全部接口 async (provider SDK 都是 IO 重操作)
- IMNormalizedMessage 是跨平台归一化 (飞书/钉钉/企微的差异在 connector 内消化)
- ConnectorRegistry 单进程内存 dict; 启动时注册各 connector class, 用 platform 字符串查
- health() 用于工作台 DatasourcesCard 显示 IM 数据源状态
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator

from app.schemas.im import IMPlatform, IMUser


@dataclass(frozen=True)
class IMNormalizedMessage:
    """跨平台归一化消息.

    各 connector 把自己的 raw event 翻译成此结构, 上层 (SignalGate / ValueSegment)
    不感知平台差异.
    """

    platform: IMPlatform
    platform_chat_id: str
    """会话 id (group_id / open_chat_id / chat_id / thread_id)."""

    platform_msg_id: str
    """原始消息 id (用于幂等去重)."""

    sender: IMUser | None
    content: str
    """正文 (text 或 markdown). 不含富文本卡片块, 卡片转 markdown."""

    mentions: list[str] = field(default_factory=list)
    """被 @ 的 user_id 列表."""

    received_at: datetime = field(default_factory=lambda: datetime.utcnow())
    raw_event_type: str = "message"
    """飞书: message; 钉钉: text; ... 仅日志/调试用."""


@dataclass(frozen=True)
class ConnectorHealth:
    """connector 健康状态 (供工作台 DatasourcesCard 显示)."""

    ok: bool
    last_event_at: datetime | None
    error_count_1h: int = 0
    note: str | None = None


@dataclass(frozen=True)
class OAuthExchangeResult:
    """OAuth code → token 兑换结果."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    tenant_name: str | None = None
    """企业名 / corp_name; 写入 IMConnection.tenant_name 用."""

    user_id: str | None = None
    """授权用户的 platform user_id."""


class IMConnector(ABC):
    """4 平台共享的接入抽象.

    各 connector 在 __init__ 接收 IMConnection 模型 (含解密后的 access_token).
    所有方法都是 async; 失败抛 ConnectorError 子类.
    """

    platform: IMPlatform

    @abstractmethod
    async def get_authorize_url(
        self, project_id: str, redirect_uri: str, state: str
    ) -> str:
        """返回 OAuth URL; 前端打开后用户授权."""

    @abstractmethod
    async def exchange_code(self, code: str) -> OAuthExchangeResult:
        """code → token (callback handler 调用)."""

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> OAuthExchangeResult:
        """access_token 过期前 5 分钟自动刷."""

    @abstractmethod
    async def revoke(self) -> None:
        """撤回授权 (本地清 token + 调 platform revoke API)."""

    @abstractmethod
    async def list_chats(self) -> list[dict]:
        """当前 user 可见的群 + 私聊."""

    @abstractmethod
    async def add_bot_to_chat(self, chat_id: str) -> None:
        """把 bot 加进群 (邀请 mode A→B 切换关键步骤)."""

    @abstractmethod
    async def list_chat_members(self, chat_id: str) -> list[IMUser]:
        """群成员列表 (用于归因)."""

    @abstractmethod
    def fetch_history(
        self,
        chat_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> AsyncIterator[IMNormalizedMessage]:
        """历史回填 (自动分页). Note: 同步签名声明 + 实现用 `async def`+`yield`."""

    @abstractmethod
    def stream_messages(self, chat_id: str) -> AsyncIterator[IMNormalizedMessage]:
        """实时事件流 (Webhook 或 Long-polling)."""

    @abstractmethod
    async def health(self) -> ConnectorHealth:
        """返回 connector 状态. 给 DatasourcesCard."""


# ─── ConnectorError 层级 ─────────────────────────────────────


class ConnectorError(Exception):
    """connector 通用错误基类."""


class OAuthExchangeError(ConnectorError):
    """code → token 兑换失败 (用户取消 / code 过期 / app_secret 错)."""


class TokenExpiredError(ConnectorError):
    """access_token 过期且 refresh 失败 (需要重新走 OAuth)."""


class ConnectorRateLimitedError(ConnectorError):
    """provider 限流; 调用方需退避后重试."""


# ─── Registry ────────────────────────────────────────────────


class _ConnectorRegistry:
    """单进程注册中心. 启动时各 connector 模块导入即注册."""

    def __init__(self) -> None:
        self._registry: dict[IMPlatform, type[IMConnector]] = {}

    def register(self, platform: IMPlatform, cls: type[IMConnector]) -> None:
        self._registry[platform] = cls

    def get(self, platform: IMPlatform) -> type[IMConnector] | None:
        return self._registry.get(platform)

    def platforms(self) -> list[IMPlatform]:
        return list(self._registry.keys())

    def clear(self) -> None:
        """测试用."""
        self._registry.clear()


registry = _ConnectorRegistry()
"""导出: from app.services.im.connector_base import registry."""
