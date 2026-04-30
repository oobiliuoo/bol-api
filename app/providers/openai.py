from typing import Dict, Any, AsyncIterator, List
import json
from app.providers.base import BaseProvider
from app.utils.http_client import AsyncHttpClient
from app.utils.sanitize import sanitize_request


class OpenAIProvider(BaseProvider):
    def __init__(self, base_url: str, api_key: str, models: List[str]):
        super().__init__(base_url, api_key, models, api_protocol="openai")

    def get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat_completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/v1/chat/completions"
        headers = self.get_headers()

        # 确保stream=False
        request = sanitize_request(request, "openai")
        request["stream"] = False

        response = await AsyncHttpClient.post(url, headers, request)
        response.raise_for_status()
        return response.json()

    async def stream_chat_completion(self, request: Dict[str, Any]) -> AsyncIterator[str]:
        url = f"{self.base_url}/v1/chat/completions"
        headers = self.get_headers()

        # 确保stream=True
        request = sanitize_request(request, "openai")
        request["stream"] = True

        async for line in AsyncHttpClient.post_stream(url, headers, request):
            yield line

    def extract_usage(self, response: Dict[str, Any]) -> Dict[str, int]:
        usage = response.get("usage", {})
        return {
            "request_tokens": usage.get("prompt_tokens", 0),
            "response_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }