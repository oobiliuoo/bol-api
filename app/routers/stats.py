from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from app.db.database import async_session
from app.db.crud import get_usage_logs, get_usage_summary, get_model_stats
from app.stats.models import UsageLogResponse, UsageSummaryResponse, ModelStatsResponse

router = APIRouter(prefix="/stats", tags=["Usage Stats"])


async def get_db():
    async with async_session() as session:
        yield session


@router.get("/logs", response_model=list[UsageLogResponse])
async def get_logs(
    api_key_id: int = Query(None),
    days: int = Query(7),
    limit: int = Query(100),
    db: AsyncSession = Depends(get_db)
):
    """获取用量日志"""
    start_time = datetime.utcnow() - timedelta(days=days)
    logs = await get_usage_logs(db, api_key_id, start_time, None, limit)
    return [
        UsageLogResponse(
            id=log.id,
            api_key_id=log.api_key_id,
            channel_id=log.channel_id,
            provider=log.provider,
            model=log.model,
            request_tokens=log.request_tokens,
            response_tokens=log.response_tokens,
            cost=log.cost,
            timestamp=log.timestamp.isoformat(),
            endpoint=log.endpoint,
            status_code=log.status_code,
            latency_ms=log.latency_ms
        )
        for log in logs
    ]


@router.get("/summary", response_model=UsageSummaryResponse)
async def get_summary(
    api_key_id: int = Query(None),
    days: int = Query(7),
    db: AsyncSession = Depends(get_db)
):
    """获取用量统计摘要"""
    summary = await get_usage_summary(db, api_key_id, days)
    return UsageSummaryResponse(**summary)


@router.get("/models", response_model=ModelStatsResponse)
async def get_model_stats_route(
    hours: int = Query(168, description="统计时长（小时）"),
    db: AsyncSession = Depends(get_db)
):
    """获取按模型分组的统计数据"""
    stats = await get_model_stats(db, hours)
    return ModelStatsResponse(**stats)