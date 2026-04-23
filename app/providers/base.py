from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, List


class BaseProvider(ABC):
    def __init__(self, base_url: str, api_key: str, models: List[str]):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.models = models

    @abstractmethod
    async def chat_completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """非流式聊天完成"""
        pass

    @abstractmethod
    async def stream_chat_completion(self, request: Dict[str, Any]) -> AsyncIterator[str]:
        """流式聊天完成"""
        pass

    def get_models(self) -> List[str]:
        """获取支持的模型列表"""
        return self.models

    def supports_model(self, model: str) -> bool:
        """检查是否支持指定模型"""
        return model in self.models or len(self.models) == 0  # 空列表表示支持所有模型