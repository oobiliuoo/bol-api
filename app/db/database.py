import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from app.config import settings

# 确保数据目录存在
db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
db_dir = os.path.dirname(db_path)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir)

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


async def init_db():
    async with engine.begin() as conn:
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


async def get_session() -> AsyncSession:
    async with async_session() as session:
        return session