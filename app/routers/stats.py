from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta, timezone
from app.db.database import get_db
from app.db.crud import get_usage_logs, get_usage_summary, get_model_stats
from app.db.models import UsageLog
from app.stats.models import UsageLogResponse, UsageSummaryResponse, ModelStatsResponse
from app.config import settings
from app.auth.jwt import verify_token

router = APIRouter(prefix="/stats", tags=["Usage Stats"])


def verify_admin(request: Request):
    """验证管理员身份（支持 JWT token 或密码）"""
    # 优先检查 JWT token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if verify_token(token):
            return True

    # 兼容旧的密码验证方式
    password = request.headers.get("X-Admin-Password")
    if password and password == settings.admin_password:
        return True

    raise HTTPException(status_code=401, detail="Invalid or expired authentication")


@router.get("/logs", response_model=dict)
async def get_logs(
    api_key_id: int = Query(None),
    days: int = Query(7),
    model: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """获取用量日志（分页 + 筛选 + 统计）"""
    start_time = datetime.now(timezone.utc) - timedelta(days=days)
    offset = (page - 1) * page_size

    # 状态码筛选
    status_code_filter = None
    if status == "200":
        status_code_filter = 200
    elif status == "499":
        status_code_filter = 499
    elif status == "error":
        status_code_filter = -1  # 表示非 200 和非 499

    logs, total, summary = await get_usage_logs(
        db, api_key_id, start_time, None, page_size, offset,
        return_count=True, return_summary=True,
        model_filter=model, status_code_filter=status_code_filter
    )

    return {
        "logs": [
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
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
        "summary": summary,
    }


@router.get("/summary", response_model=UsageSummaryResponse)
async def get_summary(
    api_key_id: int = Query(None),
    days: int = Query(7),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """获取用量统计摘要"""
    summary = await get_usage_summary(db, api_key_id, days)
    summary["request_timeout"] = settings.request_timeout
    return UsageSummaryResponse(**summary)


@router.get("/models", response_model=ModelStatsResponse)
async def get_model_stats_route(
    hours: int = Query(168, description="统计时长（小时）"),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """获取按模型分组的统计数据"""
    stats = await get_model_stats(db, hours)
    return ModelStatsResponse(**stats)


@router.get("/models/list")
async def get_models_list(
    days: int = Query(7),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """获取有日志记录的模型列表（用于筛选）"""
    start_time = datetime.now(timezone.utc) - timedelta(days=days)
    query = select(UsageLog.model).where(UsageLog.timestamp >= start_time).distinct().order_by(UsageLog.model)
    result = await db.execute(query)
    models = [row[0] for row in result.all()]
    return {"models": models}