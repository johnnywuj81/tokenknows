"""WeworkConnector · 企业微信接入骨架 (v0.3.1 K).

注:
- 当前 MVP 实现是"协议骨架": 抛 NotImplementedError 标识真正接 SDK 留 v0.4
- 与 DingTalkConnector 镜像; 真接入需要企微开放平台审批 + 申请权限

资料: https://developer.work.weixin.qq.com/document/path/91039
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


class WeworkConnector(IMConnector):
    """企业微信接入 (骨架; 真 SDK 接入留 v0.4)."""

    platform = "wework"

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
        """企微扫码授权 URL.

        生产: 替换为 https://open.work.weixin.qq.com/wwopen/sso/qrConnect
        """
        params = {
            "appid": "PLACEHOLDER_WEWORK_CORP_ID",
            "agentid": "PLACEHOLDER_WEWORK_AGENT_ID",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return (
            "https://open.work.weixin.qq.com/wwopen/sso/qrConnect?"
            + urlencode(params)
            + "#wework-not-configured"
        )

    async def exchange_code(self, code: str) -> OAuthExchangeResult:
        raise OAuthExchangeError(
            "WeworkConnector OAuth 真接入留 v0.4 (需要企微开放平台审批)"
        )

    async def refresh_token(self, refresh_token: str) -> OAuthExchangeResult:
        raise TokenExpiredError("WeworkConnector refresh 留 v0.4")

    async def revoke(self) -> None:
        logger.info("wework_revoke_local_clear")
        self._access_token = None
        self._refresh_token = None

    async def list_chats(self) -> list[dict]:
        raise NotImplementedError("Wework list_chats 留 v0.4")

    async def add_bot_to_chat(self, chat_id: str) -> None:
        raise NotImplementedError("Wework add_bot_to_chat 留 v0.4")

    async def list_chat_members(self, chat_id: str) -> list[IMUser]:
        raise NotImplementedError("Wework list_chat_members 留 v0.4")

    def fetch_history(
        self, chat_id: str, start_time: datetime, end_time: datetime
    ) -> AsyncIterator[IMNormalizedMessage]:
        async def _empty() -> AsyncIterator[IMNormalizedMessage]:
            if False:  # pragma: no cover
                yield  # type: ignore[misc]
            raise NotImplementedError("Wework fetch_history 留 v0.4")
        return _empty()

    def stream_messages(self, chat_id: str) -> AsyncIterator[IMNormalizedMessage]:
        async def _empty() -> AsyncIterator[IMNormalizedMessage]:
            if False:  # pragma: no cover
                yield  # type: ignore[misc]
            raise NotImplementedError("Wework stream_messages 留 v0.4")
        return _empty()

    async def health(self) -> ConnectorHealth:
        return ConnectorHealth(
            ok=False,
            last_event_at=None,
            note="Wework connector 真接入留 v0.4; 当前仅向导骨架可用",
        )


registry.register("wework", WeworkConnector)
