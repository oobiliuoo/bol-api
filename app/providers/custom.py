from typing import Dict, Any, AsyncIterator, List
import json
from app.providers.base import BaseProvider
from app.providers.openai import OpenAIProvider
from app.providers.anthropic import AnthropicProvider
from app.utils.http_client import AsyncHttpClient
from app.utils.sanitize import sanitize_request


class CustomProvider(BaseProvider):
    """Custom channel adapter supporting both OpenAI and Anthropic protocol formats"""

    def __init__(self, base_url: str, api_key: str, models: List[str], api_protocol: str = "openai"):
        super().__init__(base_url, api_key, models, api_protocol=api_protocol)
        self.api_protocol = api_protocol

    def get_headers(self) -> dict:
        if self.api_protocol == "anthropic":
            return {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
        else:
            return {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

    async def chat_completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        headers = self.get_headers()
        request = sanitize_request(request, "custom")
        request["stream"] = False

        if self.api_protocol == "anthropic":
            url = self._build_url("/v1/messages")
        else:
            url = self._build_url("/v1/chat/completions")

        response = await AsyncHttpClient.post(url, headers, request)
        response.raise_for_status()
        return response.json()

    async def stream_chat_completion(self, request: Dict[str, Any]) -> AsyncIterator[str]:
        headers = self.get_headers()
        request = sanitize_request(request, "custom")
        request["stream"] = True

        if self.api_protocol == "anthropic":
            url = self._build_url("/v1/messages")
        else:
            url = self._build_url("/v1/chat/completions")

        async for line in AsyncHttpClient.post_stream(url, headers, request):
            yield line

    def extract_usage(self, response: Dict[str, Any]) -> Dict[str, int]:
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
