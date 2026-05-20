"""LLM Gateway · 接口契约 (协议 / DTO / 异常).

不依赖任何 LLM SDK; 是业务代码与 LiteLLM 实现之间的稳定接口层.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# task 类型 - 决定路由 + 默认 model + 出域门禁查询
LLMTask = Literal[
    "value_extraction",   # B 模块 · 价值识别 (轻量, 高频)
    "weekly_report",      # C1 · 周报
    "tech_design",        # C2 · 技术方案
    "adr",                # C3 · ADR
    "incident",           # C4 · 问题复盘
    "redaction_llm",      # F · 脱敏 LLM 层 (轻量)
    "evidence_match",     # D · evidence 匹配兜底 (embedding)
]


class LLMMessage(BaseModel):
    """标准 OpenAI message 格式."""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMOptions(BaseModel):
    """请求参数."""

    temperature: float = 0.7
    max_tokens: int | None = None
    stream: bool = False
    json_mode: bool = False
    timeout_seconds: float = 120.0


class LLMResponse(BaseModel):
    """统一响应 DTO."""

    text: str
    usage: dict = Field(
        default_factory=dict,
        description="{prompt_tokens, completion_tokens, total_tokens}",
    )
    model_used: str
    provider: str
    latency_ms: int
    fallback_used: bool = False
    egress_blocked: bool = False  # True 表示因三层门禁降级到本地 / 拒绝


class LLMPreviewResponse(BaseModel):
    """T14 dry-run preview · 不发起真调用.

    "如果开启会发哪些字段到哪 provider" - 安全合规承诺所需.
    """

    will_send: bool
    provider: str
    model: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: float
    egress_check: dict = Field(
        default_factory=dict,
        description="{instance: bool, project: bool, task: bool, all_pass: bool}",
    )
    blocking_reason: str | None = None


# ─── 异常 ────────────────────────────────────────────────────────


class LLMGatewayError(Exception):
    """Base for all gateway errors."""


class EgressDeniedError(LLMGatewayError):
    """三层出域门禁拒绝 (instance / project / task 任一 OFF)."""

    def __init__(
        self,
        task: LLMTask,
        project_id: UUID | str | None = None,
        which_layer: str = "unknown",
    ) -> None:
        self.task = task
        self.project_id = project_id
        self.which_layer = which_layer
        super().__init__(
            f"Egress denied for task='{task}' at layer='{which_layer}' "
            f"(project={project_id})"
        )


class LicenseExpiredError(LLMGatewayError):
    """凭证过期 - 实例进入只读模式."""


class AdapterError(LLMGatewayError):
    """LiteLLM 调用底层错误 (网络 / 鉴权 / 限流)."""

    def __init__(self, provider: str, original: Exception) -> None:
        self.provider = provider
        self.original = original
        super().__init__(f"Adapter '{provider}' failed: {original}")
