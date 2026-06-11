"""启动期安全校验 · v2.1 (PAT Phase A).

main.py lifespan 调 validate_security(settings):
- 非 local 环境 + dev 默认 JWT 密钥 → RuntimeError (拒绝启动)
- local 环境 + dev 默认 JWT 密钥 → 仅 warning (本地开发不挡路)
"""

from __future__ import annotations

from app.config.logging import logger
from app.config.settings import DEV_DEFAULT_JWT_SECRET, Settings


def validate_security(settings: Settings) -> None:
    """启动期安全门禁; 配置危险且非本地 → 抛 RuntimeError, 其余警告."""
    # 非阻断警告: open 模式在非本地环境 = 数据端点可被 X-User-Id 伪造身份访问
    if settings.auth_mode == "open" and settings.environment != "local":
        logger.warning(
            "auth_mode_open_in_non_local_env",
            environment=settings.environment,
            hint="set AUTH_MODE=required for public deployments",
        )
    # 非阻断警告: CORS 通配 = 任意网页可携凭证跨域调 API
    if any(o in {"*", "null"} for o in settings.cors_origins_list):
        logger.warning(
            "cors_origins_wildcard",
            origins=settings.cors_origins_list,
            hint="list explicit origins in CORS_ORIGINS instead of '*'",
        )
    if settings.jwt_secret_key != DEV_DEFAULT_JWT_SECRET:
        return
    if settings.environment != "local":
        raise RuntimeError(
            "JWT_SECRET_KEY is the dev default; refusing to start with "
            f"environment={settings.environment!r}. Set a strong "
            "JWT_SECRET_KEY in the environment / .env file."
        )
    logger.warning(
        "jwt_secret_is_dev_default",
        hint="set JWT_SECRET_KEY before deploying beyond local",
    )


__all__ = ["validate_security"]
