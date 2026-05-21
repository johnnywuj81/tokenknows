"""HTTP API 路由."""

from fastapi import APIRouter

from app.gateway.http_api import events, generation, health, llm_preview

# 主 router - 在 main.py 内 app.include_router(api_router, prefix='/api/v1')
api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(llm_preview.router, prefix="/llm", tags=["llm"])
api_router.include_router(generation.router, tags=["generation"])
api_router.include_router(events.router, tags=["events"])
