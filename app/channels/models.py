from pydantic import BaseModel, model_validator
from typing import List, Optional


class ChannelCreate(BaseModel):
    name: str
    provider_type: str  # openai, anthropic, custom
    api_protocol: str = "openai"  # openai, anthropic - only meaningful for custom type
    base_url: str
    api_key: str
    models: List[str] = []
    priority: int = 1
    weight: float = 1.0

    @model_validator(mode="after")
    def sync_api_protocol(self):
        if self.provider_type in ("openai", "anthropic"):
            self.api_protocol = self.provider_type
        return self


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    provider_type: Optional[str] = None
    api_protocol: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    models: Optional[List[str]] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None
    weight: Optional[float] = None

    @model_validator(mode="after")
    def sync_api_protocol(self):
        if self.provider_type in ("openai", "anthropic"):
            self.api_protocol = self.provider_type
        return self


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