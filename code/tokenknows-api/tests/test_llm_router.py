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


# ─── T106 · model_override → provider 推断 ──────────────────────────


def test_infer_provider_from_model_claude() -> None:
    from app.llm_gateway.router import _infer_provider_from_model
    assert _infer_provider_from_model("claude-sonnet-4-6") == "anthropic"
    assert _infer_provider_from_model("claude-haiku-4-5") == "anthropic"


def test_infer_provider_from_model_openai() -> None:
    from app.llm_gateway.router import _infer_provider_from_model
    assert _infer_provider_from_model("gpt-4o") == "openai"
    assert _infer_provider_from_model("gpt-4o-mini") == "openai"
    assert _infer_provider_from_model("o1-mini") == "openai"
    assert _infer_provider_from_model("o3") == "openai"


def test_infer_provider_from_model_minimax() -> None:
    from app.llm_gateway.router import _infer_provider_from_model
    assert _infer_provider_from_model("abab6.5s-chat") == "minimax"


def test_infer_provider_from_model_ollama() -> None:
    from app.llm_gateway.router import _infer_provider_from_model
    assert _infer_provider_from_model("qwen2.5:3b") == "ollama"
    assert _infer_provider_from_model("qwen2.5-32b") == "ollama"
    assert _infer_provider_from_model("llama3:8b") == "ollama"
    assert _infer_provider_from_model("gpt-oss:20b") == "ollama"


def test_infer_provider_from_model_unknown_returns_none() -> None:
    from app.llm_gateway.router import _infer_provider_from_model
    assert _infer_provider_from_model("acme-secret-model") is None
    assert _infer_provider_from_model("") is None


def test_infer_provider_case_insensitive() -> None:
    from app.llm_gateway.router import _infer_provider_from_model
    assert _infer_provider_from_model("CLAUDE-3-OPUS") == "anthropic"
    assert _infer_provider_from_model(" GPT-4 ") == "openai"


def test_resolve_only_model_override_infers_provider() -> None:
    """T106 · 前端只传 model_override='gpt-4o' 时按 model 推断 provider=openai.

    避免与 task 默认 provider (可能是 anthropic/ollama) 错配.
    """
    router = LLMRouter()
    provider, model = router._resolve_provider_model(
        "weekly_report",
        model_override="gpt-4o",  # 用户选 OpenAI 模型但没显式传 provider
    )
    assert provider == "openai"  # 推断, 不是 task 默认
    assert model == "gpt-4o"


def test_resolve_unknown_model_override_falls_back_to_task_default() -> None:
    """T106 · model_override 推断失败 (acme-x) → 回退 task 默认 provider."""
    router = LLMRouter()
    task_default = router.settings.task_provider("weekly_report")
    provider, model = router._resolve_provider_model(
        "weekly_report",
        model_override="acme-x",
    )
    # 应回退到 settings 中 weekly_report 的默认 provider (受 env 控制)
    assert provider == task_default
    assert model == "acme-x"


def test_resolve_explicit_provider_override_beats_inference() -> None:
    """T106 · 显式 provider_override 优先级仍最高 (不被 prefix 推断覆盖)."""
    router = LLMRouter()
    # model name 看着是 anthropic 但用户显式指定 openai (不合理但合规)
    provider, model = router._resolve_provider_model(
        "weekly_report",
        model_override="claude-sonnet-fake",
        provider_override="openai",
    )
    assert provider == "openai"
    assert model == "claude-sonnet-fake"


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
