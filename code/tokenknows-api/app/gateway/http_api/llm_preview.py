"""POST /api/v1/llm/egress/preview · T14 dry-run.

架构红线 (TaskTechDesign T14):
    永不应出现 '用户以为没出域, 其实出了' 的状态.
    用户在 T08 切换模型 / T14 调出域开关时, 按此端点 preview 后才允许真调.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.llm_gateway.interface import LLMMessage, LLMTask
from app.llm_gateway.router import LLMRouter, get_router

router = APIRouter()


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
