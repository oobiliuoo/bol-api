from pydantic import BaseModel
from typing import Optional


class APIKeyCreate(BaseModel):
    name: Optional[str] = None


class APIKeyResponse(BaseModel):
    id: int
    name: Optional[str]
    key_prefix: Optional[str] = None
    is_active: bool
    created_at: str
    key: Optional[str] = None  # 仅在创建时返回


class APIKeyList(BaseModel):
    id: int
    name: Optional[str]
    key_prefix: Optional[str] = None
    is_active: bool
    created_at: str


class APIKeyReveal(BaseModel):
    id: int
    key: str