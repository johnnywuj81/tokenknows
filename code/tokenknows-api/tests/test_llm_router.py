"""LLMRouter.generate() · 三层门禁 + fallback + audit 测试.

mock _call_with_breaker 不真打外网.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.llm_gateway.interface import (
    AdapterError,
    EgressDeniedError,
    LLMMessage,
    LLMOptions,
    LLMResponse,
)
from app.llm_gateway.router import LLMRouter, get_router


def _msg(role: str, content: str) -> LLMMessage:
    return LLMMessage(role=role, content=content)  # type: ignore[arg-type]


def _resp(provider: str = "anthropic", text: str = "ok") -> LLMResponse:
    return LLMResponse(
        text=text,
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        model_used="x",
        provider=provider,
        latency_ms=100,
    )


# ─── _egress_check ──────────────────────────────────────────────────


def test_egress_check_instance_closed() -> None:
    router = LLMRouter()
    router.settings.instance_egress_enabled = False
    allowed, layer = router._egress_check("weekly_report", None)
    assert not allowed
    assert layer == "instance"


def test_egress_check_project_closed() -> None:
    router = LLMRouter()
    router.settings.instance_egress_enabled = True
    router.settings.default_project_egress_enabled = False
    allowed, layer = router._egress_check("weekly_report", None)
    assert not allowed
    assert layer == "project"


def test_egress_check_unknown_task() -> None:
    router = LLMRouter()
    router.settings.instance_egress_enabled = True
    router.settings.default_project_egress_enabled = True
    allowed, layer = router._egress_check("not_a_task", None)  # type: ignore[arg-type]
    assert not allowed
    assert layer == "task"


def test_egress_check_all_open() -> None:
    router = LLMRouter()
    router.settings.instance_egress_enabled = True
    router.settings.default_project_egress_enabled = True
    allowed, layer = router._egress_check("weekly_report", None)
    assert allowed
    assert layer is None


# ─── _resolve_provider_model ───────────────────────────────────────


def test_resolve_uses_task_default() -> None:
    router = LLMRouter()
    provider, model = router._resolve_provider_model("weekly_report")
    assert provider
    assert model


def test_resolve_provider_override_wins() -> None:
    router = LLMRouter()
    provider, model = router._resolve_provider_model(
        "weekly_report",
        model_override="claude-custom",
        provider_override="anthropic",
    )
    assert provider == "anthropic"
    assert model == "claude-custom"


# ─── generate · 门禁拒绝 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_raises_egress_denied_when_instance_closed() -> None:
    router = LLMRouter()
    router.settings.instance_egress_enabled = False
    with pytest.raises(EgressDeniedError):
        await router.generate(
            task="weekly_report",
            messages=[_msg("user", "x")],
        )


@pytest.mark.asyncio
async def test_generate_raises_egress_denied_when_project_closed() -> None:
    router = LLMRouter()
    router.settings.instance_egress_enabled = True
    router.settings.default_project_egress_enabled = False
    with pytest.raises(EgressDeniedError):
        await router.generate(task="weekly_report", messages=[_msg("user", "x")])


# ─── generate · 成功路径 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_returns_response_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = LLMRouter()
    router.settings.instance_egress_enabled = True
    router.settings.default_project_egress_enabled = True

    fake_breaker = AsyncMock(return_value=_resp(provider="anthropic"))
    monkeypatch.setattr(router, "_call_with_breaker", fake_breaker)
    # 防真写 audit
    with patch("app.llm_gateway.router.record_egress") as mock_audit:
        resp = await router.generate(
            task="weekly_report",
            messages=[_msg("user", "x")],
            provider_override="anthropic",
        )
    assert resp.provider == "anthropic"
    assert resp.fallback_used is False
    # cloud provider → audit 调用
    mock_audit.assert_called_once()


# ─── generate · fallback 链 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_fallback_used_when_primary_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = LLMRouter()
    router.settings.instance_egress_enabled = True
    router.settings.default_project_egress_enabled = True
    # 让 ollama 有 key (fallback chain 跳过 no_key 的)
    router.settings.anthropic_api_key = "fake-anthropic"
    router.settings.ollama_api_key = "fake-ollama"

    # primary 抛 AdapterError, 第 1 个 fallback 成功
    call_count = 0

    async def fake_breaker(provider, model, messages, options):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise AdapterError(provider, RuntimeError("503 down"))
        return _resp(provider=provider)

    monkeypatch.setattr(router, "_call_with_breaker", fake_breaker)
    with patch("app.llm_gateway.router.record_egress"):
        resp = await router.generate(
            task="weekly_report",
            messages=[_msg("user", "x")],
            provider_override="anthropic",
        )
    assert resp.fallback_used is True
    assert call_count >= 2


@pytest.mark.asyncio
async def test_generate_all_providers_fail_raises_adapter_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = LLMRouter()
    router.settings.instance_egress_enabled = True
    router.settings.default_project_egress_enabled = True

    async def always_fail(provider, model, messages, options):
        raise AdapterError(provider, RuntimeError("down"))

    monkeypatch.setattr(router, "_call_with_breaker", always_fail)
    with pytest.raises(AdapterError):
        await router.generate(
            task="weekly_report",
            messages=[_msg("user", "x")],
            provider_override="anthropic",
        )


# ─── get_router 单例 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_router_singleton() -> None:
    import app.llm_gateway.router as router_mod
    # 重置确保 fresh
    router_mod._router = None
    a = await get_router()
    b = await get_router()
    assert a is b


# ─── _call_with_breaker ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_call_with_breaker_invokes_call_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = LLMRouter()
    fake_resp = _resp(provider="anthropic")

    async def fake_call_llm(*, provider, model, messages, options):
        return fake_resp

    monkeypatch.setattr(
        "app.llm_gateway.router.call_llm", fake_call_llm,
    )
    result = await router._call_with_breaker(
        "anthropic", "claude-x", [_msg("user", "hi")], LLMOptions(),
    )
    assert result is fake_resp
