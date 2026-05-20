"""LLM Gateway · 业务代码访问 LLM 的唯一入口.

⚠ 架构铁律 (TDD §2.3): 业务代码不允许 `import anthropic / openai / minimax`.
   CI 用 ruff flake8-tidy-imports 强制. 例外: 仅 adapters/* 内部允许.

设计依据:
- TDD §6.6 (统一推理接口)
- TDD §7 (LLM Gateway 实现 + 三层门禁)
- Architecture.md §5 (核心实现)
"""

from .interface import (
    EgressDeniedError,
    LicenseExpiredError,
    LLMMessage,
    LLMOptions,
    LLMResponse,
    LLMTask,
)
from .router import LLMRouter, get_router

__all__ = [
    "EgressDeniedError",
    "LicenseExpiredError",
    "LLMMessage",
    "LLMOptions",
    "LLMResponse",
    "LLMTask",
    "LLMRouter",
    "get_router",
]
