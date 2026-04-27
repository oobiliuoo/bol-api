import httpx
from typing import AsyncIterator, Optional
import json
import asyncio


class AsyncHttpClient:
    _client: Optional[httpx.AsyncClient] = None

    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        if cls._client is None or cls._client.is_closed:
            # 大模型API可能需要较长响应时间，设置5分钟超时
            cls._client = httpx.AsyncClient(
                timeout=httpx.Timeout(300.0, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
            )
        return cls._client

    @classmethod
    async def close(cls):
        if cls._client and not cls._client.is_closed:
            await cls._client.aclose()

    @classmethod
    async def post(cls, url: str, headers: dict, json_data: dict, retries: int = 2) -> httpx.Response:
        """POST请求，支持重试"""
        client = await cls.get_client()
        last_error = None

        for attempt in range(retries + 1):
            try:
                response = await client.post(url, headers=headers, json=json_data)
                return response
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < retries:
                    await asyncio.sleep(1 + attempt)  # 递增延迟
                    continue
                raise

        raise last_error

    @classmethod
    async def post_stream(cls, url: str, headers: dict, json_data: dict, retries: int = 2) -> AsyncIterator[str]:
        """流式POST请求，支持重试"""
        client = await cls.get_client()
        last_error = None

        for attempt in range(retries + 1):
            try:
                async with client.stream("POST", url, headers=headers, json=json_data) as response:
                    # 检查响应状态
                    if response.status_code >= 400:
                        error_body = await response.aread()
                        raise httpx.HTTPStatusError(
                            f"HTTP {response.status_code}: {error_body.decode()}",
                            request=response.request,
                            response=response
                        )

                    async for line in response.aiter_lines():
                        yield line  # 保留空行，SSE格式需要空行分隔事件
                    return  # 成功完成，退出重试循环
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
                last_error = e
                if attempt < retries:
                    await asyncio.sleep(1 + attempt)
                    continue
                raise

        raise last_error