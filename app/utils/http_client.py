import httpx
from typing import AsyncIterator, Optional
import json


class AsyncHttpClient:
    _client: Optional[httpx.AsyncClient] = None

    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0))
        return cls._client

    @classmethod
    async def close(cls):
        if cls._client and not cls._client.is_closed:
            await cls._client.aclose()

    @classmethod
    async def post(cls, url: str, headers: dict, json_data: dict) -> httpx.Response:
        client = await cls.get_client()
        return await client.post(url, headers=headers, json=json_data)

    @classmethod
    async def post_stream(cls, url: str, headers: dict, json_data: dict) -> AsyncIterator[str]:
        client = await cls.get_client()
        async with client.stream("POST", url, headers=headers, json=json_data) as response:
            async for line in response.aiter_lines():
                yield line  # 保留空行，SSE格式需要空行分隔事件