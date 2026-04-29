import hashlib
import logging
import asyncio
from fastapi import Request
from starlette.responses import JSONResponse
from sqlalchemy.exc import OperationalError, InvalidRequestError
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

        # 验证API Key，带重试机制和安全的连接管理
        max_retries = 3
        api_key = None
        session = None
        try:
            for attempt in range(max_retries):
                try:
                    session = async_session()
                    api_key = await get_api_key_by_hash(session, key_hash)
                    break  # 成功则跳出重试循环
                except OperationalError as e:
                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        await asyncio.sleep(0.1 * (attempt + 1))
                        continue
                    logger.error(f"Database error during auth: {e}")
                    return JSONResponse(
                        status_code=503,
                        content={"detail": "Service temporarily unavailable"}
                    )
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    # 请求被取消或超时，直接返回错误
                    logger.warning(f"Request cancelled during auth for path {path}")
                    return JSONResponse(
                        status_code=499,
                        content={"detail": "Request cancelled"}
                    )
        finally:
            # 确保连接被正确关闭
            if session is not None:
                try:
                    await session.close()
                except Exception:
                    pass  # 忽略关闭时的错误

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