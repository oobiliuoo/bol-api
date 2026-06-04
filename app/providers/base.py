from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, List


class BaseProvider(ABC):
    def __init__(self, base_url: str, api_key: str, models: List[str], api_protocol: str = "openai"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.models = models
        self.api_protocol = api_protocol

    def _build_url(self, endpoint: str) -> str:
        """Build request URL. If base_url already contains the endpoint path, use it directly.

        For example:
          base_url="https://api.openai.com" + endpoint="/v1/chat/completions"
            -> "https://api.openai.com/v1/chat/completions"
          base_url="https://host/v2/chat/completions" + endpoint="/v1/chat/completions"
            -> "https://host/v2/chat/completions" (base_url already ends with the endpoint suffix)
        """
        # The suffix is the endpoint action, e.g. "/chat/completions" or "/messages"
        # If base_url already ends with this suffix, don't append the default endpoint
        suffix = endpoint.rsplit("/", 1)[-1]  # e.g. "completions" or "messages"
        if self.base_url.endswith("/" + suffix):
            return self.base_url
        return f"{self.base_url}{endpoint}"

    @abstractmethod
    async def chat_completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def stream_chat_completion(self, request: Dict[str, Any]) -> AsyncIterator[str]:
        pass

    def get_models(self) -> List[str]:
        return self.models

    def supports_model(self, model: str) -> bool:
        return model in self.models or len(self.models) == 0
