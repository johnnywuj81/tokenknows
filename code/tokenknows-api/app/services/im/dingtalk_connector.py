"""DingTalkConnector · 钉钉接入骨架 (v0.3.1 K).

注:
- 当前 MVP 实现是"协议骨架": 抛 NotImplementedError 标识真正接 SDK 留 v0.4
- OAuth URL 生成 + health 已实施, 让前端能通过向导跑到一半看到提示
- 真接入需要钉钉开放平台审批 + 申请权限, 暂未启动

资料: https://open.dingtalk.com/document/orgapp/dingtalk-overview
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from urllib.parse import urlencode

from app.config.logging import logger
from app.config.settings import get_settings
from app.schemas.im import IMUser
from app.services.im.connector_base import (
    ConnectorHealth,
    IMConnector,
    IMNormalizedMessage,
    OAuthExchangeError,
    OAuthExchangeResult,
    TokenExpiredError,
    registry,
)


class DingTalkConnector(IMConnector):
    """钉钉接入 (骨架; 真 SDK 接入留 v0.4)."""

    platform = "dingtalk"

    def __init__(
        self,
        access_token: str | None = None,
        refresh_token: str | None = None,
    ) -> None:
        self._settings = get_settings()
        self._access_token = access_token
        self._refresh_token = refresh_token

    async def get_authorize_url(
        self, project_id: str, redirect_uri: str, state: str
    ) -> str:
        """钉钉扫码登录 URL.

        生产: 这里要换成 OAuth 2.0 v2 endpoint
        https://oapi.dingtalk.com/connect/qrconnect?...
        """
        # 没真 app_id 配置就给 sentinel URL
        # 留 v0.4: 加 DINGTALK_APP_ID / DINGTALK_APP_SECRET settings
        params = {
            "appid": "PLACEHOLDER_DINGTALK_APP_ID",
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
            "scope": "openid",
        }
        return (
            "https://login.dingtalk.com/oauth2/auth?"
            + urlencode(params)
            + "#dingtalk-not-configured"
        )

    async def exchange_code(self, code: str) -> OAuthExchangeResult:
        raise OAuthExchangeError(
            "DingTalkConnector OAuth 真接入留 v0.4 (需要钉钉开放平台审批)"
        )

    async def refresh_token(self, refresh_token: str) -> OAuthExchangeResult:
        raise TokenExpiredError("DingTalkConnector refresh 留 v0.4")

    async def revoke(self) -> None:
        logger.info("dingtalk_revoke_local_clear")
        self._access_token = None
        self._refresh_token = None

    async def list_chats(self) -> list[dict]:
        raise NotImplementedError("DingTalk list_chats 留 v0.4")

    async def add_bot_to_chat(self, chat_id: str) -> None:
        raise NotImplementedError("DingTalk add_bot_to_chat 留 v0.4")

    async def list_chat_members(self, chat_id: str) -> list[IMUser]:
        raise NotImplementedError("DingTalk list_chat_members 留 v0.4")

    def fetch_history(
        self, chat_id: str, start_time: datetime, end_time: datetime
    ) -> AsyncIterator[IMNormalizedMessage]:
        async def _empty() -> AsyncIterator[IMNormalizedMessage]:
            if False:  # pragma: no cover
                yield  # type: ignore[misc]
            raise NotImplementedError("DingTalk fetch_history 留 v0.4")
        return _empty()

    def stream_messages(self, chat_id: str) -> AsyncIterator[IMNormalizedMessage]:
        async def _empty() -> AsyncIterator[IMNormalizedMessage]:
            if False:  # pragma: no cover
                yield  # type: ignore[misc]
            raise NotImplementedError("DingTalk stream_messages 留 v0.4")
        return _empty()

    async def health(self) -> ConnectorHealth:
        return ConnectorHealth(
            ok=False,
            last_event_at=None,
            note="DingTalk connector 真接入留 v0.4; 当前仅向导骨架可用",
        )


registry.register("dingtalk", DingTalkConnector)
