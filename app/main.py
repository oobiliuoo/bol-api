import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.db.database import init_db
from app.auth.middleware import AuthMiddleware
from app.stats.recorder import UsageRecorder
from app.routers import proxy, keys, stats, admin
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化
    await init_db()
    UsageRecorder.init()
    # 启动用量记录后台任务
    task = asyncio.create_task(UsageRecorder.process_queue())
    yield
    # 关闭时清理
    task.cancel()
    from app.utils.http_client import AsyncHttpClient
    await AsyncHttpClient.close()


app = FastAPI(
    title="bol-api",
    description="大模型API中转站",
    version="0.1.0",
    lifespan=lifespan
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件目录（不需要认证）
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 认证中间件
app.add_middleware(AuthMiddleware)

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