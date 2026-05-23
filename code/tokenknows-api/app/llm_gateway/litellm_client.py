"""LiteLLM 统一包装 · 唯一允许 import LLM SDK 的文件.

⚠ 该文件是架构铁律的例外 (TDD §2.3 + pyproject.toml banned-api).
   其它任何业务文件都禁止 import anthropic / openai / litellm.
"""

from __future__ import annotations

import time
from typing import Any

import litellm  # noqa: TID251 — 仅本文件允许

from app.config.settings import get_settings
from app.llm_gateway.interface import (
    AdapterError,
    LLMMessage,
    LLMOptions,
    LLMResponse,
)

# LiteLLM 全局配置
litellm.drop_params = True  # 丢弃 unsupported params (provider-specific 兼容)
litellm.set_verbose = False


# ─── provider → LiteLLM 调用规则 ─────────────────────────────────
#
# Anthropic: 模型名直接 "claude-sonnet-4-6" (无前缀)
# OpenAI:    "gpt-4o" (无前缀, LiteLLM 默认)
# MiniMax:   走 openai-compatible (api.minimaxi.com/v1)
#            LiteLLM 模型名: "openai/abab6.5s-chat" + api_base

def _build_litellm_kwargs(
    provider: str, model: str, messages: list[LLMMessage], options: LLMOptions
) -> dict[str, Any]:
    """根据 provider 组装 LiteLLM acompletion 参数."""
    settings = get_settings()

    base_kwargs: dict[str, Any] = {
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "temperature": options.temperature,
        "timeout": options.timeout_seconds,
    }
    if options.max_tokens:
        base_kwargs["max_tokens"] = options.max_tokens
    if options.json_mode:
        base_kwargs["response_format"] = {"type": "json_object"}
    if options.stream:
        base_kwargs["stream"] = True

    if provider == "anthropic":
        base_kwargs["model"] = model  # e.g. claude-sonnet-4-6
        base_kwargs["api_key"] = settings.anthropic_api_key

    elif provider == "openai":
        base_kwargs["model"] = model  # e.g. gpt-4o
        base_kwargs["api_key"] = settings.openai_api_key

    elif provider == "minimax":
        # MiniMax OpenAI-compatible endpoint
        base_kwargs["model"] = f"openai/{model}"
        base_kwargs["api_key"] = settings.minimax_api_key
        base_kwargs["api_base"] = settings.minimax_base_url

    elif provider == "ollama":
        # Ollama (本地 daemon 或 Ollama Cloud, 都用 OpenAI-compatible /v1/chat).
        # 模型 e.g. "gpt-oss:20b" / "minimax-m2:cloud" / "qwen3.5:397b-cloud".
        # LiteLLM 用 openai/ 前缀走 generic OpenAI client.
        base_kwargs["model"] = f"openai/{model}"
        base_kwargs["api_key"] = settings.ollama_api_key or "ollama-local"
        base_kwargs["api_base"] = settings.ollama_base_url
        # ⚠ Ollama 的 reasoning 模型 (gpt-oss / minimax-m2) 在 OpenAI 兼容端点
        # 默认会把答案放在 "reasoning" 字段, content 为空. 传 think=false
        # 让模型把答案直接放进 content. 兼容性: 非 reasoning 模型会忽略.
        base_kwargs["extra_body"] = {"think": False}

    else:
        raise AdapterError(provider, ValueError(f"Unknown provider: {provider}"))

    return base_kwargs


async def call_llm(
    *,
    provider: str,
    model: str,
    messages: list[LLMMessage],
    options: LLMOptions,
) -> LLMResponse:
    """统一调用入口. 由 LLMRouter 调用, 不直接对业务暴露.

    异常: AdapterError (鉴权 / 网络 / 限流), TimeoutError, ValueError
    """
    settings = get_settings()
    if not settings.provider_key(provider):
        raise AdapterError(provider, ValueError(f"{provider} API key not configured"))

    kwargs = _build_litellm_kwargs(provider, model, messages, options)

    start = time.monotonic()
    try:
        response = await litellm.acompletion(**kwargs)
    except Exception as exc:  # litellm 抛各种 provider 特定异常
        raise AdapterError(provider, exc) from exc
    latency_ms = int((time.monotonic() - start) * 1000)

    # 解析 LiteLLM 统一响应 (OpenAI 格式).
    # 兜底: 部分 reasoning 模型 (e.g. Ollama 的 minimax-m2:cloud) 会把答案放
    # 在 message.reasoning, content 为空. 这时用 reasoning 作为 text.
    choice = response.choices[0]
    text = choice.message.content or ""
    if not text:
        reasoning = getattr(choice.message, "reasoning", None) or getattr(
            choice.message, "reasoning_content", None
        )
        if reasoning:
            text = reasoning
    usage_obj = response.usage
    usage = {
        "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0),
        "completion_tokens": getattr(usage_obj, "completion_tokens", 0),
        "total_tokens": getattr(usage_obj, "total_tokens", 0),
    }
    actual_model = getattr(response, "model", model)

    return LLMResponse(
        text=text,
        usage=usage,
        model_used=actual_model,
        provider=provider,
        latency_ms=latency_ms,
        fallback_used=False,
        egress_blocked=False,
    )
