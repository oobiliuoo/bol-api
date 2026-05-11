import asyncio
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError
from app.db.database import async_session
from app.db.crud import create_usage_log, get_model_price
from app.db.models import UsageLog

logger = logging.getLogger(__name__)


class UsageRecorder:
    """用量记录器，异步记录API调用"""

    _queue: asyncio.Queue = None

    @classmethod
    def init(cls):
        cls._queue = asyncio.Queue()

    @classmethod
    async def record(cls, api_key_id: Optional[int], channel_id: Optional[int],
                    provider: str, model: str, endpoint: str,
                    request_tokens: int = 0, response_tokens: int = 0,
                    cost: float = 0.0, status_code: int = 200, latency_ms: int = 0):
        """异步记录用量"""
        if cls._queue is None:
            cls.init()

        await cls._queue.put({
            "api_key_id": api_key_id,
            "channel_id": channel_id,
            "provider": provider,
            "model": model,
            "endpoint": endpoint,
            "request_tokens": request_tokens,
            "response_tokens": response_tokens,
            "cost": cost,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc),
        })

    @classmethod
    async def process_queue(cls):
        """处理队列中的用量记录，带重试机制和安全的连接管理"""
        if cls._queue is None:
            return

        while True:
            try:
                data = await asyncio.wait_for(cls._queue.get(), timeout=1.0)

                # 重试机制：最多重试 3 次
                max_retries = 3
                last_error = None
                for attempt in range(max_retries):
                    session = None
                    try:
                        session = async_session()
                        await create_usage_log(session, **data)
                        await session.commit()
                        break  # 成功则跳出重试循环
                    except OperationalError as e:
                        last_error = e
                        if "database is locked" in str(e) and attempt < max_retries - 1:
                            # 数据库锁定，等待后重试
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        logger.error(f"Database error recording usage: {e}")
                    except asyncio.CancelledError:
                        logger.info("Usage recorder cancelled during write")
                        raise
                    except Exception as e:
                        logger.error(f"Unexpected error recording usage: {e}")
                        last_error = e
                    finally:
                        if session:
                            try:
                                await session.close()
                            except Exception:
                                pass

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                # 队列处理任务被取消，优雅退出
                logger.info("Usage recorder queue processing cancelled")
                raise
            except Exception as e:
                logger.error(f"Error recording usage: {e}")

    @classmethod
    async def drain(cls, timeout: float = 5.0):
        """等待队列清空，最多等待 timeout 秒"""
        if cls._queue is None:
            return
        deadline = time.monotonic() + timeout
        while not cls._queue.empty() and time.monotonic() < deadline:
            await asyncio.sleep(0.1)

    @classmethod
    async def cleanup_old_logs(cls, retention_days: int = 90):
        """清理超过保留期限的用量日志"""
        try:
            session = async_session()
            try:
                cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
                stmt = delete(UsageLog).where(UsageLog.timestamp < cutoff)
                result = await session.execute(stmt)
                await session.commit()
                deleted = result.rowcount
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} usage logs older than {retention_days} days")
            finally:
                await session.close()
        except Exception as e:
            logger.warning(f"Cleanup task failed: {e}")

    @classmethod
    async def start_cleanup_task(cls, interval_hours: int = 1, retention_days: int = 90):
        """启动定期清理后台任务"""
        while True:
            await asyncio.sleep(interval_hours * 3600)
            await cls.cleanup_old_logs(retention_days)


async def calculate_cost(session: AsyncSession, model: str, request_tokens: int, response_tokens: int) -> float:
    """计算费用，使用 $/M (每百万token) 单位"""
    price = await get_model_price(session, model)

    if not price or not price.is_active:
        # 无价格配置时返回0
        return 0.0

    input_cost = (request_tokens / 1_000_000) * price.input_price
    output_cost = (response_tokens / 1_000_000) * price.output_price
    return input_cost + output_cost