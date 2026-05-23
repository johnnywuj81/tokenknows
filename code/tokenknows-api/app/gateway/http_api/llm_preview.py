"""POST /api/v1/llm/egress/preview · T14 dry-run + T109 provider status.

架构红线 (TaskTechDesign T14):
    永不应出现 '用户以为没出域, 其实出了' 的状态.
    用户在 T08 切换模型 / T14 调出域开关时, 按此端点 preview 后才允许真调.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config.settings import get_settings
from app.llm_gateway.interface import LLMMessage, LLMTask
from app.llm_gateway.router import LLMRouter, get_router

router = APIRouter()


# ── T109 · GET /llm/providers/status ──────────────────────────────


class ProviderStatus(BaseModel):
    """单个 provider 配置状态 (不真探测网络, 仅看 key 是否配置)."""

    name: Literal["anthropic", "openai", "minimax", "ollama"]
    models: list[str]
    """该 provider 在本实例 settings 中出现的所有 model name."""
    configured: bool
    """key 是否非空; ollama 不需要 key 总为 True."""
    status: Literal["configured", "key_missing"]
    """语义: configured = 可尝试调用; key_missing = 必失败."""


class PreviewRequest(BaseModel):
    task: LLMTask
    messages: list[LLMMessage]
    project_id: UUID | str | None = None
    model_override: str | None = None
    provider_override: str | None = None


@router.post("/egress/preview")
async def egress_preview(
    body: PreviewRequest,
    router_instance: LLMRouter = Depends(get_router),
) -> dict[str, Any]:
    """dry-run · 不发起真 LLM 调用, 返回 '如果开启会发哪些字段去哪 provider'."""
    return router_instance.preview(
        task=body.task,
        messages=body.messages,
        project_id=body.project_id,
        model_override=body.model_override,
        provider_override=body.provider_override,
    )


@router.get("/providers/status", response_model=list[ProviderStatus])
async def list_provider_status() -> list[ProviderStatus]:
    """v1.8 T109 · 返回 4 个 provider 的配置状态 + 当前用到的 model 集合.

    不真探测网络 (那需要后台异步轮询, MVP 不做); 仅看 key 是否非空.
    前端 LlmEgressPanel 用此替换 hard-coded 状态字符串.
    """
    s = get_settings()

    # 聚合每个 provider 在 settings 中出现的所有 model
    # (task_*_provider/model 已配置的 task)
    tasks = (
        "value_extraction", "weekly_report", "tech_design", "adr",
        "incident", "book", "agent_skill", "knowledge_graph", "redaction_llm",
    )
    models_by_provider: dict[str, set[str]] = {
        "anthropic": set(), "openai": set(), "minimax": set(), "ollama": set(),
    }
    for t in tasks:
        prov = s.task_provider(t)
        mod = s.task_model(t)
        if prov in models_by_provider:
            models_by_provider[prov].add(mod)

    # fallback chain 中的 model 也算 (用户可能切换到这些)
    from app.llm_gateway.router import FALLBACK_CHAIN
    for primary, chain in FALLBACK_CHAIN.items():
        for fb_prov, fb_model in chain:
            if fb_prov in models_by_provider:
                models_by_provider[fb_prov].add(fb_model)

    out: list[ProviderStatus] = []
    for prov in ("anthropic", "openai", "minimax", "ollama"):
        key = s.provider_key(prov)
        # ollama 用占位 'ollama-local' 也算 configured
        configured = bool(key) and key != ""
        out.append(ProviderStatus(
            name=prov,  # type: ignore[arg-type]
            models=sorted(models_by_provider[prov]),
            configured=configured,
            status="configured" if configured else "key_missing",
        ))
    return out
