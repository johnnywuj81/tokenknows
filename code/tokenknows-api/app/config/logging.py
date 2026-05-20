"""结构化日志 · structlog JSON 输出 + Trace ID 注入.

简化版 (移植自 digital_enterprise/app/config/logging.py 思路).
"""

from __future__ import annotations

import logging

import structlog


def setup_logging(level: str = "INFO") -> None:
    """配置 structlog (本地: 漂亮控制台; 生产: JSON 行)."""
    logging.basicConfig(format="%(message)s", level=level.upper())

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger()
