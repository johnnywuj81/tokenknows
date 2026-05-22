"""TokenKnows API · FastAPI 入口.

启动:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

OpenAPI: <http://localhost:8000/docs>
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config.logging import logger, setup_logging
from app.config.settings import get_settings
from app.gateway.http_api import api_router
from app.persistence import bootstrap as bootstrap_db
from app.services.generation_service import _bootstrap_from_db
from app.services.im import retention as im_retention
from app.services.im import token_refresher as im_token_refresher
from app.services.auto_trigger import scheduler as auto_trigger_scheduler
from app.services.auto_trigger_service import bootstrap as bootstrap_auto_trigger
from app.services.im_service import bootstrap as bootstrap_im
from app.services.skill_service import bootstrap as bootstrap_skills

# v0.3 · IM 保留期清理扫描间隔 (秒). 默认 1 小时.
# 测试模式下 (PYTEST_CURRENT_TEST 环境变量存在) 不启动后台 task.
_RETENTION_SWEEP_INTERVAL_SECONDS = 3600
# v0.3.1 I · token 刷新间隔 (秒). 默认 10 分钟.
_TOKEN_REFRESH_INTERVAL_SECONDS = 600


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动 + 关闭钩子."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info(
        "tokenknows_api_starting",
        version=__version__,
        environment=settings.environment,
        instance_egress_enabled=settings.instance_egress_enabled,
        has_anthropic_key=bool(settings.anthropic_api_key),
        has_openai_key=bool(settings.openai_api_key),
        has_minimax_key=bool(settings.minimax_api_key),
    )
    # P1 · SQLite 持久化: 启动时把 state.sqlite 全量加载进内存 dict
    bootstrap_db()
    _bootstrap_from_db()
    # v0.2 · skills 内存 cache (cache-aside)
    bootstrap_skills()
    # v0.3 · IM connections 内存 cache
    bootstrap_im()
    # v0.4 · Auto-Trigger 规则与执行历史 (T26: 仅记录数量; T27 才启动调度器)
    bootstrap_auto_trigger()

    # v0.3.1 P1 + I · 启动 IM 后台 task (retention 清理 + token 刷新)
    # 测试模式下不启 (避免污染 TestClient 测试 + 干扰 fixture)
    bg_tasks: list[asyncio.Task] = []
    if not _is_test_mode():
        bg_tasks.append(asyncio.create_task(
            im_retention.retention_sweep_loop(_RETENTION_SWEEP_INTERVAL_SECONDS),
            name="im-retention-sweep",
        ))
        logger.info(
            "im_retention_sweep_started",
            interval_seconds=_RETENTION_SWEEP_INTERVAL_SECONDS,
        )
        bg_tasks.append(asyncio.create_task(
            im_token_refresher.token_refresher_loop(_TOKEN_REFRESH_INTERVAL_SECONDS),
            name="im-token-refresher",
        ))
        logger.info(
            "im_token_refresher_started",
            interval_seconds=_TOKEN_REFRESH_INTERVAL_SECONDS,
        )

        # v0.4 · 启动 APScheduler (T27: 6 个固定 job, 大多是 stub; T29/T31 替换为真)
        auto_trigger_scheduler.start_scheduler()

    yield

    # v0.4 · 优雅关停 APScheduler (在 IM bg task 之前停, 防止 job 触发后没人处理)
    if not _is_test_mode():
        auto_trigger_scheduler.shutdown_scheduler(wait=False)

    # 优雅关停后台 task
    for task in bg_tasks:
        task.cancel()
    for task in bg_tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
    if bg_tasks:
        logger.info("im_background_tasks_stopped", count=len(bg_tasks))
    logger.info("tokenknows_api_stopping")


def _is_test_mode() -> bool:
    """检测当前是否在 pytest 运行 (避免后台 task 污染测试)."""
    import os
    return "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("DISABLE_IM_RETENTION") == "1"


app = FastAPI(
    title="TokenKnows API",
    version=__version__,
    description="FastAPI 后端 + LLM Gateway (三层出域门禁 + LiteLLM 多家适配)",
    lifespan=lifespan,
)

# CORS - 仅本地开发允许 Vite dev server (5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载主 API 路由
app.include_router(api_router, prefix="/api/v1")
