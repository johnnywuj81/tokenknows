"""TokenKnows API · FastAPI 入口.

启动:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

OpenAPI: <http://localhost:8000/docs>
"""

from __future__ import annotations

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
    yield
    logger.info("tokenknows_api_stopping")


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
