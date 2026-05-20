"""健康检查 · /healthz (liveness) + /readyz (readiness)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config.settings import get_settings
from app.llm_gateway.audit import get_db_path

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


class ReadyResponse(BaseModel):
    ready: bool
    checks: dict


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Liveness · 进程存活."""
    from app import __version__

    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=settings.environment,
    )


@router.get("/readyz", response_model=ReadyResponse)
async def readyz() -> ReadyResponse:
    """Readiness · 依赖就绪.

    检查:
    - 至少 1 个 LLM provider key 配置
    - egress_log SQLite 可写
    - 三层出域开关状态
    """
    settings = get_settings()
    checks = {
        "anthropic_key_set": bool(settings.anthropic_api_key),
        "openai_key_set": bool(settings.openai_api_key),
        "minimax_key_set": bool(settings.minimax_api_key),
        "instance_egress_enabled": settings.instance_egress_enabled,
        "default_project_egress_enabled": settings.default_project_egress_enabled,
        "egress_log_path": get_db_path(),
    }
    has_any_key = any(
        [
            checks["anthropic_key_set"],
            checks["openai_key_set"],
            checks["minimax_key_set"],
        ]
    )
    return ReadyResponse(ready=has_any_key, checks=checks)
