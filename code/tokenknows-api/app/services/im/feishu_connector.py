"""FeishuConnector · 飞书个人助理模式 OAuth (v0.3 T18).

来源:
- engineering_handoff/tasks/T18-feishu-oauth.md
- Proposal_IM_KnowledgeDistillation_v0.3.md §9.3

实施范围 (T18):
- 4 个 OAuth 方法 (get_authorize_url / exchange_code / refresh_token / revoke)
- callback handler 由 app/gateway/http_api/im_webhooks.py 调用
- 不实现 list_chats / fetch_history / stream_messages (T19 接)
- 不依赖 lark-oapi SDK (避免重量依赖, 直接 httpx + 飞书 OpenAPI)

OAuth scopes:
  im:message im:chat:readonly im:chat contact:user.id:readonly
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.config.logging import logger
from app.config.settings import get_settings
from app.schemas.im import IMUser
from app.services.im.connector_base import (
    ConnectorError,
    ConnectorHealth,
    IMConnector,
    IMNormalizedMessage,
    OAuthExchangeError,
    OAuthExchangeResult,
    TokenExpiredError,
    registry,
)

_FEISHU_SCOPES = "im:message im:chat:readonly im:chat contact:user.id:readonly"
"""OAuth 申请的权限范围 (空格分隔)."""

_DEFAULT_TIMEOUT = 30.0


class FeishuConnector(IMConnector):
    """飞书个人助理模式 connector.

    创建方式:
        conn = FeishuConnector(access_token=..., refresh_token=...)
    OAuth 阶段时, access_token=None, 走 get_authorize_url + exchange_code.
    """

    platform = "feishu"

    def __init__(
        self,
        access_token: str | None = None,
        refresh_token: str | None = None,
    ) -> None:
        self._settings = get_settings()
        self._access_token = access_token
        self._refresh_token = refresh_token

    # ─── 内部 HTTP ──────────────────────────────────────

    @property
    def _base(self) -> str:
        return self._settings.feishu_api_base.rstrip("/")

    def _ensure_app_credentials(self) -> tuple[str, str]:
        if not self._settings.feishu_app_id or not self._settings.feishu_app_secret:
            raise OAuthExchangeError(
                "FEISHU_APP_ID / FEISHU_APP_SECRET 未配置; 请在 .env 中设置"
            )
        return self._settings.feishu_app_id, self._settings.feishu_app_secret

    async def _post_json(
        self, path: str, json_body: dict, headers: dict | None = None
    ) -> dict:
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, json=json_body, headers=headers or {})
        if resp.status_code != 200:
            raise OAuthExchangeError(
                f"飞书 POST {path} 失败: HTTP {resp.status_code} {resp.text[:200]}"
            )
        data = resp.json()
        if data.get("code") not in (0, None):
            raise OAuthExchangeError(
                f"飞书 POST {path} 错误码 {data.get('code')}: {data.get('msg')}"
            )
        return data

    async def _app_access_token(self) -> str:
        """app_access_token (内部 API 用, 与 user access_token 不同).

        cache 留 v0.3 后期; MVP 每次 OAuth 都重取一次.
        """
        app_id, app_secret = self._ensure_app_credentials()
        data = await self._post_json(
            "/open-apis/auth/v3/app_access_token/internal",
            {"app_id": app_id, "app_secret": app_secret},
        )
        token = data.get("app_access_token")
        if not token:
            raise OAuthExchangeError("飞书 app_access_token 响应缺字段")
        return token

    # ─── OAuth 4 方法 ───────────────────────────────────

    async def get_authorize_url(
        self,
        project_id: str,
        redirect_uri: str,
        state: str,
    ) -> str:
        """生成 OAuth 授权 URL.

        state 包含 connection_id, callback handler 验证并查询对应 connection.
        """
        app_id, _ = self._ensure_app_credentials()
        params = {
            "app_id": app_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": _FEISHU_SCOPES,
        }
        return f"{self._base}/open-apis/authen/v1/authorize?{urlencode(params)}"

    async def exchange_code(self, code: str) -> OAuthExchangeResult:
        """code → access_token + refresh_token."""
        app_token = await self._app_access_token()
        data = await self._post_json(
            "/open-apis/authen/v1/access_token",
            {"grant_type": "authorization_code", "code": code},
            headers={"Authorization": f"Bearer {app_token}"},
        )
        payload = data.get("data") or {}
        return self._build_exchange_result(payload)

    async def refresh_token(self, refresh_token: str) -> OAuthExchangeResult:
        """access_token 过期前 5 分钟刷."""
        if not refresh_token:
            raise TokenExpiredError("refresh_token 为空; 需要重新走 OAuth")
        app_token = await self._app_access_token()
        try:
            data = await self._post_json(
                "/open-apis/authen/v1/refresh_access_token",
                {"grant_type": "refresh_token", "refresh_token": refresh_token},
                headers={"Authorization": f"Bearer {app_token}"},
            )
        except OAuthExchangeError as e:
            raise TokenExpiredError(f"refresh_token 失败: {e}") from e
        payload = data.get("data") or {}
        return self._build_exchange_result(payload)

    async def revoke(self) -> None:
        """飞书无 revoke API; 本地清 token 即可."""
        logger.info("feishu_oauth_revoke_local_clear", platform="feishu")
        self._access_token = None
        self._refresh_token = None

    def _build_exchange_result(self, payload: dict) -> OAuthExchangeResult:
        """从飞书 payload 提取 token 字段."""
        access = payload.get("access_token")
        if not access:
            raise OAuthExchangeError(f"飞书响应缺 access_token: {payload!r}")
        expires_in = payload.get("expires_in") or 7200
        expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))
        return OAuthExchangeResult(
            access_token=access,
            refresh_token=payload.get("refresh_token"),
            expires_at=expires_at,
            tenant_name=payload.get("tenant_key") or payload.get("enterprise_name"),
            user_id=payload.get("open_id") or payload.get("user_id"),
        )

    # ─── T19 群 / 消息 ────────────────────────────────

    async def _get_with_token(self, path: str, params: dict | None = None) -> dict:
        """带 user access_token 的 GET (业务接口)."""
        if not self._access_token:
            raise TokenExpiredError("access_token 缺; 需要重新授权")
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(
                url,
                params=params or {},
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
        if resp.status_code == 401:
            raise TokenExpiredError(f"飞书 401 鉴权失败: {resp.text[:200]}")
        if resp.status_code != 200:
            raise ConnectorError(
                f"飞书 GET {path} HTTP {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json()
        if data.get("code") not in (0, None):
            raise ConnectorError(
                f"飞书 GET {path} code={data.get('code')} msg={data.get('msg')}"
            )
        return data

    async def _post_with_token(self, path: str, json_body: dict) -> dict:
        if not self._access_token:
            raise TokenExpiredError("access_token 缺; 需要重新授权")
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                url, json=json_body,
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
        if resp.status_code == 401:
            raise TokenExpiredError(f"飞书 401 鉴权失败: {resp.text[:200]}")
        if resp.status_code != 200:
            raise ConnectorError(
                f"飞书 POST {path} HTTP {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json()
        if data.get("code") not in (0, None):
            raise ConnectorError(
                f"飞书 POST {path} code={data.get('code')} msg={data.get('msg')}"
            )
        return data

    async def list_chats(self) -> list[dict]:
        """当前 user 可见的群 + 私聊.

        返回每条含 chat_id / name / chat_type / description.
        """
        data = await self._get_with_token(
            "/open-apis/im/v1/chats", params={"page_size": 50}
        )
        items = (data.get("data") or {}).get("items") or []
        return items

    async def add_bot_to_chat(self, chat_id: str) -> None:
        """把 bot 加进群. member_type=app, member_id=app_id."""
        # 鉴权优先: 缺 access_token 直接抛 TokenExpiredError (与 _get/_post_with_token 行为一致)
        if not self._access_token:
            raise TokenExpiredError("access_token 缺; 需要重新授权")
        app_id, _ = self._ensure_app_credentials()
        await self._post_with_token(
            f"/open-apis/im/v1/chats/{chat_id}/members",
            {
                "id_list": [app_id],
                "member_id_type": "app_id",
            },
        )

    async def list_chat_members(self, chat_id: str) -> list[IMUser]:
        """群成员列表."""
        data = await self._get_with_token(
            f"/open-apis/im/v1/chats/{chat_id}/members",
            params={"page_size": 100},
        )
        items = (data.get("data") or {}).get("items") or []
        out: list[IMUser] = []
        for it in items:
            out.append(IMUser(
                user_id=it.get("member_id") or it.get("open_id") or "",
                name=it.get("name"),
            ))
        return out

    def fetch_history(
        self, chat_id: str, start_time: datetime, end_time: datetime
    ) -> AsyncIterator[IMNormalizedMessage]:
        """历史消息回填 (自动翻页)."""

        async def _gen() -> AsyncIterator[IMNormalizedMessage]:
            page_token: str | None = None
            while True:
                params = {
                    "container_id_type": "chat",
                    "container_id": chat_id,
                    "start_time": str(int(start_time.timestamp() * 1000)),
                    "end_time": str(int(end_time.timestamp() * 1000)),
                    "page_size": 50,
                }
                if page_token:
                    params["page_token"] = page_token
                data = await self._get_with_token(
                    "/open-apis/im/v1/messages", params=params
                )
                payload = data.get("data") or {}
                items = payload.get("items") or []
                for raw in items:
                    msg = self._normalize_message(raw, chat_id)
                    if msg is not None:
                        yield msg
                page_token = payload.get("page_token")
                if not page_token:
                    break

        return _gen()

    def stream_messages(self, chat_id: str) -> AsyncIterator[IMNormalizedMessage]:
        """实时事件流.

        MVP: 复用 fetch_history(now - 5min, now), 调用方 sleep 5min 再 next().
        生产: Webhook 推到 Redis pub/sub, 这里订阅.
        """

        async def _gen() -> AsyncIterator[IMNormalizedMessage]:
            from datetime import timedelta
            now = datetime.now(UTC)
            async for msg in self.fetch_history(
                chat_id, now - timedelta(minutes=5), now
            ):
                yield msg

        return _gen()

    def _normalize_message(
        self, raw: dict, chat_id: str
    ) -> IMNormalizedMessage | None:
        """飞书 message 对象 → IMNormalizedMessage. None=跳过 (e.g. 系统消息)."""
        msg_type = raw.get("msg_type") or raw.get("message_type")
        if msg_type and msg_type not in ("text", "post", "interactive"):
            # 富媒体卡片暂不蒸馏; 后续 T20 SignalGate 也会 noise 掉
            return None
        body = raw.get("body") or {}
        content_raw = body.get("content") or raw.get("content") or ""
        if isinstance(content_raw, dict):
            text = content_raw.get("text") or ""
        else:
            text = str(content_raw)
        if not text:
            return None
        sender = raw.get("sender") or {}
        sender_user = IMUser(
            user_id=sender.get("id") or sender.get("sender_id") or "",
            name=sender.get("name"),
        )
        # mentions
        mentions: list[str] = []
        for m in raw.get("mentions") or []:
            uid = m.get("id") or m.get("open_id")
            if uid:
                mentions.append(uid)
        # 时间戳: 飞书 create_time 是毫秒字符串
        ts_raw = raw.get("create_time") or raw.get("received_at")
        received = datetime.now(UTC)
        try:
            if ts_raw:
                received = datetime.fromtimestamp(int(ts_raw) / 1000, tz=UTC)
        except (ValueError, TypeError):
            pass
        return IMNormalizedMessage(
            platform="feishu",
            platform_chat_id=chat_id,
            platform_msg_id=raw.get("message_id") or raw.get("id") or "",
            sender=sender_user,
            content=text,
            mentions=mentions,
            received_at=received,
            raw_event_type=msg_type or "message",
        )

    async def health(self) -> ConnectorHealth:
        """简单健康检查: 凭据齐 = ok."""
        ok = bool(
            self._settings.feishu_app_id and self._settings.feishu_app_secret
        )
        note = None if ok else "FEISHU_APP_ID / FEISHU_APP_SECRET 未配置"
        return ConnectorHealth(ok=ok, last_event_at=None, note=note)


# 注册
registry.register("feishu", FeishuConnector)
