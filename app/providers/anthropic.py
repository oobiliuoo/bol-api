from typing import Dict, Any, AsyncIterator, List
import json
from app.providers.base import BaseProvider
from app.utils.http_client import AsyncHttpClient
from app.utils.sanitize import sanitize_request


class AnthropicProvider(BaseProvider):
    def __init__(self, base_url: str, api_key: str, models: List[str]):
        super().__init__(base_url, api_key, models, api_protocol="anthropic")

    def get_headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    async def chat_completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        url = self._build_url("/v1/messages")
        headers = self.get_headers()

        request = sanitize_request(request, "anthropic")
        request["stream"] = False

        response = await AsyncHttpClient.post(url, headers, request)
        response.raise_for_status()
        return response.json()

    async def stream_chat_completion(self, request: Dict[str, Any]) -> AsyncIterator[str]:
        url = self._build_url("/v1/messages")
        headers = self.get_headers()

        request = sanitize_request(request, "anthropic")
        request["stream"] = True

        async for line in AsyncHttpClient.post_stream(url, headers, request):
            yield line

    def extract_usage(self, response: Dict[str, Any]) -> Dict[str, int]:
        usage = response.get("usage", {})
        return {
            "request_tokens": usage.get("input_tokens", 0),
            "response_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        }
