"""LLMRouter · 路由 + 三层出域门禁 + CircuitBreaker + fallback + 审计.

设计依据 Architecture.md §5.3-5.4 + TDD §7.3-7.4

调用全流程:
    1. select_adapter(task, project_id) - 含三层门禁
    2. CircuitBreaker.call(litellm_client)
    3. 失败 → fallback 链 (排除已失败 provider)
    4. cloud 调用强制 record_egress
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from app.config.logging import logger
from app.config.settings import get_settings
from app.core.resilience import CircuitOpenError, get_circuit_breaker
from app.llm_gateway.audit import record_egress
from app.llm_gateway.interface import (
    AdapterError,
    EgressDeniedError,
    LLMMessage,
    LLMOptions,
    LLMResponse,
    LLMTask,
)
from app.llm_gateway.litellm_client import call_llm

# 哪些 provider 是 cloud (写 egress_log).
# Ollama 包含本地 (gpt-oss:20b) 和 cloud (xxx:cloud) 模型; 为保守起见
# 列为 cloud, 所有调用都审计.
CLOUD_PROVIDERS = {"anthropic", "openai", "minimax", "ollama"}

# fallback 链: 主 provider 失败时按序尝试.
# Ollama 放在每条链尾兜底 - 当外网 / 第三方 key 都不可用时仍能产出.
FALLBACK_CHAIN: dict[str, list[tuple[str, str]]] = {
    "anthropic": [
        ("openai", "gpt-4o"),
        ("minimax", "abab6.5s-chat"),
        ("ollama", "minimax-m2:cloud"),
    ],
    "openai": [
        ("anthropic", "claude-sonnet-4-5-20250929"),
        ("minimax", "abab6.5s-chat"),
        ("ollama", "minimax-m2:cloud"),
    ],
    "minimax": [
        ("openai", "gpt-4o-mini"),
        ("anthropic", "claude-haiku-4-5"),
        ("ollama", "minimax-m2:cloud"),
    ],
    "ollama": [
        ("anthropic", "claude-haiku-4-5"),
        ("openai", "gpt-4o-mini"),
    ],
}


# T106 · model name prefix → provider 推断表 (前端只传 model name 时兜底)
# 顺序敏感: 更具体的 prefix (e.g. 'gpt-oss') 要排在更泛的 ('gpt') 之前
_MODEL_PREFIX_TO_PROVIDER: list[tuple[str, str]] = [
    ("claude", "anthropic"),
    ("gpt-oss", "ollama"),  # 必须先于 'gpt' 匹配
    ("gpt", "openai"),
    ("o1", "openai"),
    ("o3", "openai"),
    ("abab", "minimax"),
    ("minimax", "ollama"),  # 'minimax-m2:cloud' 通过 ollama litellm 适配
    ("qwen", "ollama"),
    ("llama", "ollama"),
    ("deepseek", "ollama"),
]


def _infer_provider_from_model(model: str) -> str | None:
    """根据 model name 前缀推断 provider.

    e.g. 'claude-sonnet-4-6' → 'anthropic'
         'gpt-4o' / 'o1-mini' → 'openai'
         'abab6.5s-chat' → 'minimax'
         'qwen2.5-32b' / 'minimax-m2:cloud' → 'ollama'

    未匹配返回 None (调用方 fallback 到 task 默认 provider).
    """
    name = model.lower().strip()
    for prefix, provider in _MODEL_PREFIX_TO_PROVIDER:
        if name.startswith(prefix):
            return provider
    return None


class LLMRouter:
    """LLM 调用编排器 - 业务代码通过此类访问 LLM."""

    def __init__(self) -> None:
        self.settings = get_settings()

    # ─── 三层出域门禁 ───────────────────────────────────────────

    def _egress_check(
        self, task: LLMTask, project_id: UUID | str | None
    ) -> tuple[bool, str | None]:
        """检查三层门禁. 返回 (allowed, blocking_layer)."""
        # 1. instance 级 (env / 实例 admin 控制)
        if not self.settings.instance_egress_enabled:
            return False, "instance"

        # 2. project 级 (MVP: 用 default; 生产读 DB project.llm_egress_enabled)
        if not self.settings.default_project_egress_enabled:
            return False, "project"

        # 3. task 级 (MVP: 全部允许; 生产读 DB project.task_egress_config[task])
        # 这里检查 task 是否有 provider 映射 (已配置即允许)
        try:
            _ = self.settings.task_provider(task)
        except ValueError:
            return False, "task"

        return True, None

    # ─── 适配器路由 ───────────────────────────────────────────

    def _resolve_provider_model(
        self,
        task: LLMTask,
        model_override: str | None = None,
        provider_override: str | None = None,
    ) -> tuple[str, str]:
        """决定本次用哪个 provider + model.

        优先级:
            1. provider_override + model_override 都给 → 直接用
            2. 只给 model_override (前端旧版 dialog) → 按 model name 前缀推断 provider,
               避免 'anthropic+gpt-4o' 这种错配 (T106)
            3. 都不给 → task 默认 (settings.task_provider/task_model)
        """
        # T106: 显式 provider_override 优先级最高
        if provider_override:
            provider = provider_override
        elif model_override:
            # 按 model name 前缀推断 provider (鲁棒兜底)
            provider = _infer_provider_from_model(model_override) or self.settings.task_provider(task)
        else:
            provider = self.settings.task_provider(task)
        model = model_override or self.settings.task_model(task)
        return provider, model

    # ─── 单次调用 (含 CircuitBreaker + fallback) ─────────────────

    async def _call_with_breaker(
        self,
        provider: str,
        model: str,
        messages: list[LLMMessage],
        options: LLMOptions,
    ) -> LLMResponse:
        """通过 CircuitBreaker 调用 (失败计数)."""
        breaker = get_circuit_breaker(
            name=f"llm-{provider}",
            failure_threshold=3,
            recovery_timeout=30.0,
        )
        return await breaker.call(call_llm,
                                  provider=provider,
                                  model=model,
                                  messages=messages,
                                  options=options)

    async def _call_with_fallback(
        self,
        primary_provider: str,
        primary_model: str,
        messages: list[LLMMessage],
        options: LLMOptions,
    ) -> tuple[LLMResponse, bool]:
        """主 provider 失败 → 走 fallback 链. 返回 (response, fallback_used)."""
        try:
            response = await self._call_with_breaker(
                primary_provider, primary_model, messages, options
            )
            return response, False
        except (CircuitOpenError, AdapterError, TimeoutError) as primary_err:
            logger.warning(
                "primary_provider_failed",
                provider=primary_provider,
                error=str(primary_err),
            )

        # 逐个尝试 fallback
        for fb_provider, fb_model in FALLBACK_CHAIN.get(primary_provider, []):
            if not self.settings.provider_key(fb_provider):
                logger.info("fallback_skipped_no_key", provider=fb_provider)
                continue
            try:
                logger.info("trying_fallback", provider=fb_provider, model=fb_model)
                response = await self._call_with_breaker(
                    fb_provider, fb_model, messages, options
                )
                response.fallback_used = True
                response.provider = fb_provider
                response.model_used = response.model_used or fb_model
                return response, True
            except (CircuitOpenError, AdapterError, TimeoutError) as fb_err:
                logger.warning(
                    "fallback_provider_failed",
                    provider=fb_provider,
                    error=str(fb_err),
                )
                continue

        # 全部 provider 失败
        raise AdapterError(primary_provider, RuntimeError("All providers failed"))

    # ─── 公开 API ─────────────────────────────────────────────

    async def generate(
        self,
        task: LLMTask,
        messages: list[LLMMessage],
        options: LLMOptions | None = None,
        project_id: UUID | str | None = None,
        user_id: UUID | str | None = None,
        model_override: str | None = None,
        provider_override: str | None = None,
    ) -> LLMResponse:
        """主入口 · 业务调用唯一通道.

        实现 TDD §7.4 全流程: 门禁 → CircuitBreaker → fallback → audit
        """
        opts = options or LLMOptions()

        # 1. 三层门禁 - 任一 OFF 抛 EgressDeniedError
        allowed, blocking_layer = self._egress_check(task, project_id)
        if not allowed:
            raise EgressDeniedError(
                task=task,
                project_id=project_id,
                which_layer=blocking_layer or "unknown",
            )

        # 2. 决定 provider / model
        provider, model = self._resolve_provider_model(
            task, model_override, provider_override
        )

        # 3. 调用 + fallback
        response, fallback_used = await self._call_with_fallback(
            provider, model, messages, opts
        )

        # 4. 审计 (cloud only)
        if response.provider in CLOUD_PROVIDERS:
            # 不阻塞主流程 - 审计写失败仅日志告警
            try:
                record_egress(
                    task=task,
                    provider=response.provider,
                    model=response.model_used,
                    messages=messages,
                    response=response,
                    project_id=project_id,
                    user_id=user_id,
                    fallback_used=fallback_used,
                )
            except Exception as audit_err:
                logger.error("egress_audit_write_failed", error=str(audit_err))

        return response

    # ─── T14 dry-run preview ────────────────────────────────────

    def preview(
        self,
        task: LLMTask,
        messages: list[LLMMessage],
        project_id: UUID | str | None = None,
        model_override: str | None = None,
        provider_override: str | None = None,
    ) -> dict[str, Any]:
        """不发起真调用 - 返回 '如果开启会发哪些字段去哪 provider'.

        架构红线 (TaskTechDesign T14): 永不应出现 '用户以为没出域,其实出了' 的状态.
        """
        allowed, blocking_layer = self._egress_check(task, project_id)
        provider, model = self._resolve_provider_model(
            task, model_override, provider_override
        )
        est_input = sum(len(m.content) for m in messages) // 3  # 粗略 1 token ≈ 3 chars
        est_output = 1500  # 估算

        return {
            "will_send": allowed,
            "provider": provider,
            "model": model,
            "estimated_input_tokens": est_input,
            "estimated_output_tokens": est_output,
            "egress_check": {
                "instance": self.settings.instance_egress_enabled,
                "project": self.settings.default_project_egress_enabled,
                "task": True,
                "all_pass": allowed,
            },
            "blocking_reason": (
                f"出域被 {blocking_layer} 层拒绝" if not allowed else None
            ),
        }


# ─── 单例 ──────────────────────────────────────────────────────

_router: LLMRouter | None = None
_router_lock = asyncio.Lock()


async def get_router() -> LLMRouter:
    """FastAPI 依赖注入用."""
    global _router
    if _router is None:
        async with _router_lock:
            if _router is None:
                _router = LLMRouter()
    return _router
