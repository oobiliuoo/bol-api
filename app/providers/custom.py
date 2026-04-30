from typing import Dict, Any, AsyncIterator, List
import json
from app.providers.base import BaseProvider
from app.providers.openai import OpenAIProvider
from app.providers.anthropic import AnthropicProvider
from app.utils.http_client import AsyncHttpClient
from app.utils.sanitize import sanitize_request


class CustomProvider(BaseProvider):
    """自定义渠道适配器，支持OpenAI和Anthropic两种协议格式"""

    def __init__(self, base_url: str, api_key: str, models: List[str], api_protocol: str = "openai"):
        super().__init__(base_url, api_key, models, api_protocol=api_protocol)
        self.api_protocol = api_protocol

    def get_headers(self) -> dict:
        """根据协议类型返回不同的headers"""
        if self.api_protocol == "anthropic":
            return {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
        else:  # openai format
            return {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

    async def chat_completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """根据协议类型发送不同格式的请求"""
        headers = self.get_headers()
        request = sanitize_request(request, "custom")
        request["stream"] = False

        if self.api_protocol == "anthropic":
            # Anthropic格式: 使用 /v1/messages 端点
            url = f"{self.base_url}/v1/messages"
        else:
            # OpenAI格式: 使用 /v1/chat/completions 端点
            url = f"{self.base_url}/v1/chat/completions"

        response = await AsyncHttpClient.post(url, headers, request)
        response.raise_for_status()
        return response.json()

    async def stream_chat_completion(self, request: Dict[str, Any]) -> AsyncIterator[str]:
        """流式请求"""
        headers = self.get_headers()
        request = sanitize_request(request, "custom")
        request["stream"] = True

        if self.api_protocol == "anthropic":
            url = f"{self.base_url}/v1/messages"
        else:
            url = f"{self.base_url}/v1/chat/completions"

        async for line in AsyncHttpClient.post_stream(url, headers, request):
            yield line

    def extract_usage(self, response: Dict[str, Any]) -> Dict[str, int]:
        """根据协议类型提取用量信息"""
        usage = response.get("usage", {})
        if self.api_protocol == "anthropic":
            return {
                "request_tokens": usage.get("input_tokens", 0),
                "response_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            }
        else:
            return {
                "request_tokens": usage.get("prompt_tokens", 0),
                "response_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }