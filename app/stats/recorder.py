import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError
from app.db.database import async_session
from app.db.crud import create_usage_log, get_model_price

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
        """处理队列中的用量记录，带重试机制"""
        if cls._queue is None:
            return

        while True:
            try:
                data = await asyncio.wait_for(cls._queue.get(), timeout=1.0)

                # 重试机制：最多重试 3 次
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        async with async_session() as session:
                            await create_usage_log(session, **data)
                        break  # 成功则跳出重试循环
                    except OperationalError as e:
                        if "database is locked" in str(e) and attempt < max_retries - 1:
                            # 数据库锁定，等待后重试
                            await asyncio.sleep(0.5 * (attempt + 1))  # 递增等待时间
                            continue
                        raise  # 其他错误或最后一次重试失败，抛出异常

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error recording usage: {e}")


async def calculate_cost(session: AsyncSession, model: str, request_tokens: int, response_tokens: int) -> float:
    """计算费用，使用 $/M (每百万token) 单位"""
    price = await get_model_price(session, model)

    if not price or not price.is_active:
        # 无价格配置时返回0
        return 0.0

    input_cost = (request_tokens / 1_000_000) * price.input_price
    output_cost = (response_tokens / 1_000_000) * price.output_price
    return input_cost + output_cost