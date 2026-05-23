"""TokenKnows backend HTTP client · MCP server 内部用.

设计原则:
  - 同进程跑可直接 import backend service (zero-network); 跨进程跑走 HTTP
  - 默认 HTTP (8001) 让 plugin 可独立于 backend 部署
  - timeout 30s; backend pipeline 长 (LLM call) 30-60s, 用户用 distill 命令时
    显式说"约 1 分钟", 不阻塞 MCP request 默认超时
"""

from __future__ import annotations

import os
from typing import Any

import httpx


DEFAULT_TIMEOUT = 60.0


class TokenKnowsClient:
    """轻量 HTTP wrapper for tokenknows-api.

    使用:
        client = TokenKnowsClient()
        asset = await client.post('/api/v1/projects/p1/assets/generate',
                                  json={'type': 'weekly_report'})
    """

    def __init__(
        self,
        base_url: str | None = None,
        auth_token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv("TOKENKNOWS_API_BASE")
            or "http://127.0.0.1:8001"
        ).rstrip("/")
        self.auth_token = auth_token or os.getenv("TOKENKNOWS_API_TOKEN")
        self.timeout = timeout
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.auth_token:
            self._headers["Authorization"] = f"Bearer {self.auth_token}"

    async def get(self, path: str, params: dict | None = None) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            r = await cli.get(
                f"{self.base_url}{path}", params=params, headers=self._headers,
            )
            r.raise_for_status()
            return r.json()

    async def post(self, path: str, json: dict | None = None) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            r = await cli.post(
                f"{self.base_url}{path}", json=json or {}, headers=self._headers,
            )
            r.raise_for_status()
            return r.json()

    async def patch(self, path: str, json: dict | None = None) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            r = await cli.patch(
                f"{self.base_url}{path}", json=json or {}, headers=self._headers,
            )
            r.raise_for_status()
            return r.json()


_default_client: TokenKnowsClient | None = None


def get_client() -> TokenKnowsClient:
    """单例; tests 可 monkeypatch."""
    global _default_client
    if _default_client is None:
        _default_client = TokenKnowsClient()
    return _default_client


def set_client(client: TokenKnowsClient) -> None:
    """测试注入用."""
    global _default_client
    _default_client = client
