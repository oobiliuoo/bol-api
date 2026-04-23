from pydantic import BaseModel
from typing import List, Optional


class ChannelCreate(BaseModel):
    name: str
    provider_type: str  # openai, anthropic, custom
    api_protocol: str = "openai"  # openai, anthropic - API请求格式
    base_url: str
    api_key: str
    models: List[str] = []
    priority: int = 1
    weight: float = 1.0


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    api_protocol: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    models: Optional[List[str]] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None
    weight: Optional[float] = None


class ChannelResponse(BaseModel):
    id: int
    name: str
    provider_type: str
    api_protocol: str
    base_url: str
    models: List[str]
    is_active: bool
    priority: int
    weight: float