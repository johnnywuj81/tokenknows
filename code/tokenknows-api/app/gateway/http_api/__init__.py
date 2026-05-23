"""HTTP API 路由."""

from fastapi import APIRouter

from app.gateway.http_api import (
    auth,
    auto_trigger,
    entities,
    events,
    generation,
    health,
    im,
    im_webhooks,
    llm_preview,
    members,
    notifications,
    skills,
    webhooks,
)

# 主 router - 在 main.py 内 app.include_router(api_router, prefix='/api/v1')
api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(llm_preview.router, prefix="/llm", tags=["llm"])
api_router.include_router(generation.router, tags=["generation"])
api_router.include_router(events.router, tags=["events"])
api_router.include_router(webhooks.router, tags=["webhooks"])
api_router.include_router(skills.router, tags=["skills"])              # v0.2
api_router.include_router(im.router, tags=["im"])                      # v0.3 REST API
api_router.include_router(im_webhooks.router, tags=["im"])             # v0.3 webhook
api_router.include_router(auto_trigger.router, tags=["auto-trigger"])  # v0.4 T32
api_router.include_router(notifications.router)                        # v0.5.1 T49+T51
api_router.include_router(members.router)                              # v0.9.0 T66
api_router.include_router(auth.router)                                 # v1.1.0 T74
api_router.include_router(entities.router, tags=["entities"])          # v1.3.1 T96
