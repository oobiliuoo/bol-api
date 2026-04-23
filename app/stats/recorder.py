import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from app.db.database import async_session
from app.db.crud import create_usage_log


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
            "timestamp": datetime.utcnow(),
        })

    @classmethod
    async def process_queue(cls):
        """处理队列中的用量记录"""
        if cls._queue is None:
            return

        while True:
            try:
                data = await asyncio.wait_for(cls._queue.get(), timeout=1.0)
                async with async_session() as session:
                    await create_usage_log(session, **data)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Error recording usage: {e}")


def calculate_cost(provider: str, model: str, request_tokens: int, response_tokens: int) -> float:
    """计算费用（简单估算）"""
    # 简化价格表，实际应该从配置读取
    prices = {
        "gpt-4": {"input": 0.03, "output": 0.06},  # 每1k tokens
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        "claude-3-opus": {"input": 0.015, "output": 0.075},
        "claude-3-sonnet": {"input": 0.003, "output": 0.015},
        "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    }

    price = prices.get(model, {"input": 0.001, "output": 0.002})  # 默认价格
    input_cost = (request_tokens / 1000) * price["input"]
    output_cost = (response_tokens / 1000) * price["output"]
    return input_cost + output_cost