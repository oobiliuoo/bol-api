from pydantic import BaseModel
from typing import Optional, List


class UsageLogResponse(BaseModel):
    id: int
    api_key_id: Optional[int]
    channel_id: Optional[int]
    provider: str
    model: str
    request_tokens: int
    response_tokens: int
    cost: float
    timestamp: str
    endpoint: str
    status_code: int
    latency_ms: int


class UsageSummaryResponse(BaseModel):
    total_requests: int
    total_request_tokens: int
    total_response_tokens: int
    total_tokens: int
    total_cost: float
    days: int
    rpm: float
    tpm: float


class ModelStat(BaseModel):
    model: str
    requests: int
    request_tokens: int
    response_tokens: int
    cost: float
    p50_latency: int = 0
    peak_latency: int = 0


class ModelStatsResponse(BaseModel):
    stats: List[ModelStat]
    total_requests: int
    total_tokens: int
    total_cost: float
    total_p50: int = 0
    total_peak: int = 0
    period: str
    hours: int
