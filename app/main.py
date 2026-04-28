import asyncio
import warnings
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.db.database import init_db
from app.auth.middleware import setup_auth_middleware
from app.stats.recorder import UsageRecorder
from app.routers import proxy, keys, stats, admin
from app.utils.logger import setup_logging, get_logger
import os

# 初始化日志系统
setup_logging(log_dir="logs", log_level="INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化
    logger.info("Starting bol-api server...")
    await init_db()
    logger.info("Database initialized")
    UsageRecorder.init()
    logger.info("Usage recorder initialized")
    # 启动用量记录后台任务
    task = asyncio.create_task(UsageRecorder.process_queue())

    # 安全检查：警告使用默认密钥
    if settings.encryption_key == "default_encryption_key_32_bytes!":
        warnings.warn(
            "WARNING: Using default ENCRYPTION_KEY. Set a secure key in production!",
            UserWarning
        )
        logger.warning("Using default ENCRYPTION_KEY. Set a secure key in production!")
    if settings.jwt_secret == "default_jwt_secret_change_in_production!":
        warnings.warn(
            "WARNING: Using default JWT_SECRET. Set a secure key in production!",
            UserWarning
        )
        logger.warning("Using default JWT_SECRET. Set a secure key in production!")

    logger.info("bol-api server started successfully")

    yield

    # 关闭时清理
    logger.info("Shutting down bol-api server...")
    task.cancel()
    try:
        await task  # 等待任务真正取消
    except asyncio.CancelledError:
        pass  # 任务被取消是预期行为

    from app.utils.http_client import AsyncHttpClient
    await AsyncHttpClient.close()
    logger.info("bol-api server shutdown complete")


app = FastAPI(
    title="bol-api",
    description="大模型API中转站",
    version="0.1.0",
    lifespan=lifespan
)

# CORS配置 - 注意：allow_origins=["*"] 和 allow_credentials=True 不能同时使用
# 生产环境应配置具体的 allow_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为具体域名
    allow_credentials=False,  # 与 allow_origins=["*"] 配合必须为 False
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件目录（不需要认证）
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 认证中间件（使用 @app.middleware("http") 方式）
setup_auth_middleware(app)

# 注册路由
app.include_router(proxy.router)
app.include_router(keys.router)
app.include_router(stats.router)
app.include_router(admin.router)


@app.get("/")
async def root():
    return {"message": "bol-api is running", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}