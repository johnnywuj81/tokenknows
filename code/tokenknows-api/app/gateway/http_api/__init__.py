"""HTTP API 路由."""

from fastapi import APIRouter, Depends

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
    projects,
    skills,
    tokens,
    webhooks,
)
from app.gateway.http_api._session import require_auth_if_required

# v2.1 · AUTH_MODE 门禁: 挂在全部数据 router 上.
# 保持开放的只有: health (探活) / webhooks + im_webhooks (HMAC/签名自带鉴权,
# 不走 Bearer) / auth (登录本身不能要求已登录).
# auth_mode='open' (默认) 时门禁直接放行, 对现有部署零影响.
_auth_gate = [Depends(require_auth_if_required)]

# 主 router - 在 main.py 内 app.include_router(api_router, prefix='/api/v1')
api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(
    llm_preview.router, prefix="/llm", tags=["llm"], dependencies=_auth_gate
)
api_router.include_router(
    generation.router, tags=["generation"], dependencies=_auth_gate
)
api_router.include_router(events.router, tags=["events"], dependencies=_auth_gate)
api_router.include_router(webhooks.router, tags=["webhooks"])
api_router.include_router(
    skills.router, tags=["skills"], dependencies=_auth_gate
)  # v0.2
api_router.include_router(
    im.router, tags=["im"], dependencies=_auth_gate
)  # v0.3 REST API
api_router.include_router(im_webhooks.router, tags=["im"])             # v0.3 webhook
api_router.include_router(
    auto_trigger.router, tags=["auto-trigger"], dependencies=_auth_gate
)  # v0.4 T32
api_router.include_router(
    notifications.router, dependencies=_auth_gate
)  # v0.5.1 T49+T51
api_router.include_router(members.router, dependencies=_auth_gate)     # v0.9.0 T66
api_router.include_router(auth.router)                                 # v1.1.0 T74
api_router.include_router(tokens.router, dependencies=_auth_gate)      # v2.1 PAT
api_router.include_router(
    entities.router, tags=["entities"], dependencies=_auth_gate
)  # v1.3.1 T96
api_router.include_router(
    projects.router, tags=["projects"], dependencies=_auth_gate
)  # v2.0 T141 (移出 MSW mock)
