import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from app.config import settings

# 确保数据目录存在
db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
db_dir = os.path.dirname(db_path)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir)

# SQLite 优化配置：
# - timeout: 增加锁等待时间到 30 秒
# - check_same_thread: 允许多线程访问
# - pool_size: 连接池大小
# - max_overflow: 允许超出 pool_size 的连接数
# - pool_timeout: 获取连接的超时时间
# - pool_recycle: 连接回收时间（秒）
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    connect_args={
        "timeout": 30,
        "check_same_thread": False,
    }
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


async def init_db():
    async with engine.begin() as conn:
        # 启用 WAL 模式 - 允许读写并发
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        # 设置 busy_timeout - 等待锁释放的时间（毫秒）
        await conn.execute(text("PRAGMA busy_timeout=30000"))
        # 启用同步模式 - NORMAL 比 FULL 性能更好，安全性足够
        await conn.execute(text("PRAGMA synchronous=NORMAL"))
        # 设置缓存大小 - 负数表示 KB，正数表示页数
        await conn.execute(text("PRAGMA cache_size=-64000"))  # 64MB

        await conn.run_sync(Base.metadata.create_all)

        # 为现有表添加索引（如果不存在）
        # SQLite 不支持 IF NOT EXISTS for CREATE INDEX，需要先检查
        indexes = [
            ("idx_usage_log_api_key_id", "usage_logs", "api_key_id"),
            ("idx_usage_log_channel_id", "usage_logs", "channel_id"),
            ("idx_usage_log_model", "usage_logs", "model"),
        ]

        for idx_name, table, column in indexes:
            try:
                await conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})"))
            except Exception:
                pass  # 索引可能已存在


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """公共数据库会话依赖，用于 FastAPI Depends"""
    async with async_session() as session:
        yield session