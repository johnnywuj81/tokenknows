"""litellm_client · _build_litellm_kwargs + call_llm 单测.

call_llm 用 unittest.mock.patch 替换 litellm.acompletion (不真打外网).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm_gateway.interface import AdapterError, LLMMessage, LLMOptions
from app.llm_gateway.litellm_client import _build_litellm_kwargs, call_llm


def _msg(role: str, content: str) -> LLMMessage:
    return LLMMessage(role=role, content=content)  # type: ignore[arg-type]


# ─── _build_litellm_kwargs · provider 路由 ─────────────────────────


def test_build_kwargs_anthropic_no_prefix() -> None:
    kw = _build_litellm_kwargs(
        "anthropic",
        "claude-sonnet-4-6",
        [_msg("user", "hi")],
        LLMOptions(),
    )
    assert kw["model"] == "claude-sonnet-4-6"   # 无前缀
    assert "api_key" in kw
    assert kw["messages"][0] == {"role": "user", "content": "hi"}


def test_build_kwargs_openai_no_prefix() -> None:
    kw = _build_litellm_kwargs(
        "openai", "gpt-4o", [_msg("user", "x")], LLMOptions(),
    )
    assert kw["model"] == "gpt-4o"
    assert "api_key" in kw


def test_build_kwargs_minimax_openai_compat() -> None:
    """MiniMax 走 openai/ 前缀 + api_base 指向 minimaxi.com."""
    kw = _build_litellm_kwargs(
        "minimax", "abab6.5s", [_msg("user", "x")], LLMOptions(),
    )
    assert kw["model"].startswith("openai/")
    assert "api_base" in kw


def test_build_kwargs_ollama_includes_think_false() -> None:
    """Ollama reasoning 模型 think=false (避免 content 空)."""
    kw = _build_litellm_kwargs(
        "ollama", "minimax-m2:cloud", [_msg("user", "x")], LLMOptions(),
    )
    assert kw["model"].startswith("openai/")
    assert kw["extra_body"]["think"] is False


def test_build_kwargs_unknown_provider_raises() -> None:
    with pytest.raises(AdapterError):
        _build_litellm_kwargs("nonexistent", "m", [_msg("user", "x")], LLMOptions())


def test_build_kwargs_json_mode_sets_response_format() -> None:
    kw = _build_litellm_kwargs(
        "anthropic", "x", [_msg("user", "x")],
        LLMOptions(json_mode=True),
    )
    assert kw["response_format"]["type"] == "json_object"


def test_build_kwargs_stream_true() -> None:
    kw = _build_litellm_kwargs(
        "anthropic", "x", [_msg("user", "x")],
        LLMOptions(stream=True),
    )
    assert kw["stream"] is True


def test_build_kwargs_max_tokens_carried() -> None:
    kw = _build_litellm_kwargs(
        "anthropic", "x", [_msg("user", "x")],
        LLMOptions(max_tokens=512),
    )
    assert kw["max_tokens"] == 512


def test_build_kwargs_default_temperature() -> None:
    kw = _build_litellm_kwargs(
        "anthropic", "x", [_msg("user", "x")], LLMOptions(),
    )
    assert "temperature" in kw


# ─── call_llm · mock acompletion ────────────────────────────────────


def _make_mock_response(content: str = "ok", model: str = "x") -> SimpleNamespace:
    """模拟 LiteLLM response 对象 (OpenAI 兼容 shape)."""
    choice = SimpleNamespace(message=SimpleNamespace(content=content))
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return SimpleNamespace(choices=[choice], usage=usage, model=model)


@pytest.mark.asyncio
async def test_call_llm_returns_llm_response() -> None:
    fake = AsyncMock(return_value=_make_mock_response("hello world"))
    with patch("app.llm_gateway.litellm_client.litellm.acompletion", fake):
        resp = await call_llm(
            provider="anthropic", model="claude-x",
            messages=[_msg("user", "hi")], options=LLMOptions(),
        )
    assert resp.text == "hello world"
    assert resp.usage["prompt_tokens"] == 10
    assert resp.usage["completion_tokens"] == 5
    assert resp.provider == "anthropic"
    assert resp.latency_ms >= 0
    assert resp.fallback_used is False
    assert resp.egress_blocked is False


@pytest.mark.asyncio
async def test_call_llm_provider_exception_wrapped_in_adapter_error() -> None:
    fake = AsyncMock(side_effect=RuntimeError("rate limit"))
    with patch("app.llm_gateway.litellm_client.litellm.acompletion", fake):
        with pytest.raises(AdapterError):
            await call_llm(
                provider="anthropic", model="x",
                messages=[_msg("user", "x")], options=LLMOptions(),
            )


@pytest.mark.asyncio
async def test_call_llm_reasoning_fallback_when_content_empty() -> None:
    """Ollama 的 reasoning 模型 content 为空, 取 reasoning 字段."""
    choice = SimpleNamespace(
        message=SimpleNamespace(content="", reasoning="actual answer here"),
    )
    usage = SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    resp_obj = SimpleNamespace(choices=[choice], usage=usage, model="m")
    fake = AsyncMock(return_value=resp_obj)
    with patch("app.llm_gateway.litellm_client.litellm.acompletion", fake):
        resp = await call_llm(
            provider="anthropic", model="m",
            messages=[_msg("user", "x")], options=LLMOptions(),
        )
    assert resp.text == "actual answer here"


@pytest.mark.asyncio
async def test_call_llm_missing_api_key_raises_adapter_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """provider_key 返 None → 不调 acompletion, 直接 AdapterError."""
    from app.config.settings import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    with pytest.raises(AdapterError):
        await call_llm(
            provider="anthropic", model="x",
            messages=[_msg("user", "x")], options=LLMOptions(),
        )
