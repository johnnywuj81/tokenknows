"""TokenKnows backend HTTP client · MCP server 内部用.

设计原则:
  - 同进程跑可直接 import backend service (zero-network); 跨进程跑走 HTTP
  - 默认 HTTP (8001) 让 plugin 可独立于 backend 部署
  - timeout 30s; backend pipeline 长 (LLM call) 30-60s, 用户用 distill 命令时
    显式说"约 1 分钟", 不阻塞 MCP request 默认超时
  - 错误翻译: httpx 底层异常 → TokenKnowsAPIError, 带双语可操作提示,
    让 MCP host (Claude) 直接把"怎么修"转述给用户
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_TIMEOUT = 60.0

_DEPLOY_GUIDE = "https://github.com/johnnywuj81/tokenknows#quick-start"


class TokenKnowsAPIError(RuntimeError):
    """backend 调用失败的统一异常 (双语单行提示, 含修复指引)."""


def _connect_error_message(base_url: str) -> str:
    """ConnectError/ConnectTimeout → 提示启动 backend 或改 TOKENKNOWS_API_BASE."""
    return (
        f"Cannot connect to TokenKnows backend at {base_url}; start it with "
        f"`uvicorn app.main:app --port 8001` or point TOKENKNOWS_API_BASE to a "
        f"running instance (deploy guide: {_DEPLOY_GUIDE})"
        f" · 无法连接 TokenKnows backend ({base_url}): 请先用 "
        f"`uvicorn app.main:app --port 8001` 启动, 或把 TOKENKNOWS_API_BASE "
        f"指向已部署实例 (部署指南: {_DEPLOY_GUIDE})."
    )


def _auth_error_message(status: int) -> str:
    """401/403 → 提示去 web UI 项目设置 → MCP 接入 创建 token."""
    web = os.getenv("TOKENKNOWS_WEB_BASE", "http://127.0.0.1:5173").rstrip("/")
    return (
        f"Authentication failed ({status}); create a token in the web UI "
        f"({web}) under 项目设置 → MCP 接入, set TOKENKNOWS_API_TOKEN, then "
        f"reconnect MCP"
        f" · 认证失败 ({status}): 请在 web UI ({web}) 的 项目设置 → MCP 接入 "
        f"页创建 token, 设置环境变量 TOKENKNOWS_API_TOKEN 后重连 MCP."
    )


def _project_not_found_message(path: str) -> str:
    """404 on /api/v1/projects/{pid}/... → 提示检查 TOKENKNOWS_DEFAULT_PROJECT."""
    pid = path.removeprefix("/api/v1/projects/").split("/")[0]
    return (
        f"Project '{pid}' not found (404); check TOKENKNOWS_DEFAULT_PROJECT "
        f"and the project list in the web UI"
        f" · 项目 '{pid}' 不存在 (404): 请检查环境变量 "
        f"TOKENKNOWS_DEFAULT_PROJECT, 并在 web UI 里确认项目列表."
    )


def _read_timeout_message() -> str:
    """ReadTimeout → distill pipeline 慢属正常, 提示稍后轮询."""
    return (
        "Request timed out; the distill pipeline can take 30-60s, retry "
        "get_asset shortly"
        " · 请求超时: 蒸馏流水线约需 30-60 秒, 稍后重试 get_asset 轮询即可."
    )


def _status_error_message(exc: httpx.HTTPStatusError, path: str) -> str:
    """HTTPStatusError → 按状态码分派双语提示."""
    status = exc.response.status_code
    if status in (401, 403):
        return _auth_error_message(status)
    if status == 404 and path.startswith("/api/v1/projects/"):
        return _project_not_found_message(path)
    body = exc.response.text[:200]
    return (
        f"TokenKnows API returned {status} for {path}: {body}"
        f" · TokenKnows API 返回 {status} ({path}): {body}"
    )


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

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> Any:
        """统一请求入口: get/post/patch 共用 + httpx 错误翻译成 TokenKnowsAPIError."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as cli:
                r = await cli.request(
                    method,
                    f"{self.base_url}{path}",
                    params=params,
                    json=json,
                    headers=self._headers,
                )
                r.raise_for_status()
                return r.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise TokenKnowsAPIError(_connect_error_message(self.base_url)) from exc
        except httpx.TimeoutException as exc:
            # ReadTimeout / WriteTimeout / PoolTimeout 统一按"后端慢"处理
            # (ConnectTimeout 已被上一分支按"连不上"捕获)
            raise TokenKnowsAPIError(_read_timeout_message()) from exc
        except httpx.HTTPStatusError as exc:
            raise TokenKnowsAPIError(_status_error_message(exc, path)) from exc

    async def get(self, path: str, params: dict | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: dict | None = None) -> Any:
        return await self._request("POST", path, json=json or {})

    async def patch(self, path: str, json: dict | None = None) -> Any:
        return await self._request("PATCH", path, json=json or {})


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
