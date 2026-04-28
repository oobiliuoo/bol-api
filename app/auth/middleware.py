import hashlib
import logging
from fastapi import Request
from starlette.responses import JSONResponse
from app.db.database import async_session
from app.db.crud import get_api_key_by_hash

logger = logging.getLogger(__name__)


def setup_auth_middleware(app):
    """设置认证中间件"""
    # 不需要认证的路径前缀（路由级别有自己的认证）
    PUBLIC_PREFIXES = [
        "/admin",
        "/stats",
        "/static",
        "/docs",
        "/openapi.json",
        "/health",
    ]
    # 精确匹配的公开路径
    PUBLIC_EXACT = [
        "/",
    ]

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path

        # 检查精确匹配
        if path in PUBLIC_EXACT:
            return await call_next(request)

        # 检查前缀匹配
        for prefix in PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # 需要认证的路径
        # 支持两种认证方式: Authorization: Bearer 和 x-api-key
        auth_header = request.headers.get("Authorization", "")
        x_api_key = request.headers.get("x-api-key", "")

        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # 移除 "Bearer " 前缀
        elif x_api_key:
            token = x_api_key

        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header"}
            )
        key_hash = hashlib.sha256(token.encode()).hexdigest()

        # 验证API Key
        async with async_session() as session:
            api_key = await get_api_key_by_hash(session, key_hash)
            if not api_key:
                logger.warning(f"Authentication failed: invalid API key for path {path}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid API key"}
                )
            if not api_key.is_active:
                logger.warning(f"Authentication failed: disabled API key {api_key.id} for path {path}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "API key is disabled"}
                )

            # 注入API Key信息到请求状态
            request.state.api_key_id = api_key.id
            request.state.api_key_name = api_key.name
            logger.debug(f"API key {api_key.id} ({api_key.name}) authenticated for {path}")

        return await call_next(request)


def verify_admin_password(password: str, settings) -> bool:
    return password == settings.admin_password