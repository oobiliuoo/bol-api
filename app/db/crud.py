import secrets
import hashlib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import APIKey, Channel, UsageLog, ModelPrice
from datetime import datetime, timedelta
from typing import Optional, List
from app.utils.encryption import encrypt_key, decrypt_key, is_encrypted


async def create_api_key(session: AsyncSession, name: Optional[str] = None) -> tuple[str, APIKey]:
    raw_key = f"bol-{secrets.token_urlsafe(28)}"  # 添加前缀便于识别
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12] + "..." + raw_key[-4:]  # 显示前12位和后4位
    encrypted_key = encrypt_key(raw_key)  # 加密存储
    api_key = APIKey(
        key_hash=key_hash,
        encrypted_key=encrypted_key,
        key_prefix=key_prefix,
        name=name
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return raw_key, api_key


async def get_api_key_by_hash(session: AsyncSession, key_hash: str) -> Optional[APIKey]:
    result = await session.execute(select(APIKey).where(APIKey.key_hash == key_hash))
    return result.scalar_one_or_none()


async def get_api_key_by_id(session: AsyncSession, key_id: int) -> Optional[APIKey]:
    result = await session.execute(select(APIKey).where(APIKey.id == key_id))
    return result.scalar_one_or_none()


async def get_all_api_keys(session: AsyncSession) -> List[APIKey]:
    result = await session.execute(select(APIKey).order_by(APIKey.created_at.desc()))
    return result.scalars().all()


async def delete_api_key(session: AsyncSession, key_id: int) -> bool:
    result = await session.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()
    if api_key:
        await session.delete(api_key)
        await session.commit()
        return True
    return False


async def toggle_api_key(session: AsyncSession, key_id: int, is_active: bool) -> Optional[APIKey]:
    result = await session.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()
    if api_key:
        api_key.is_active = is_active
        await session.commit()
        await session.refresh(api_key)
        return api_key
    return None


async def create_channel(session: AsyncSession, name: str, provider_type: str, base_url: str,
                         api_key: str, models: List[str], priority: int = 1, weight: float = 1.0,
                         api_protocol: str = "openai") -> Channel:
    channel = Channel(
        name=name,
        provider_type=provider_type,
        api_protocol=api_protocol,
        base_url=base_url,
        api_key=api_key,
        models=models,
        priority=priority,
        weight=weight
    )
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return channel


async def get_all_channels(session: AsyncSession) -> List[Channel]:
    result = await session.execute(select(Channel).order_by(Channel.priority.desc()))
    return result.scalars().all()


async def get_active_channels(session: AsyncSession) -> List[Channel]:
    result = await session.execute(
        select(Channel).where(Channel.is_active == True).order_by(Channel.priority.desc())
    )
    return result.scalars().all()


async def get_channel_by_id(session: AsyncSession, channel_id: int) -> Optional[Channel]:
    result = await session.execute(select(Channel).where(Channel.id == channel_id))
    return result.scalar_one_or_none()


# 渠道可更新字段白名单
CHANNEL_UPDATE_FIELDS = {"name", "api_protocol", "base_url", "api_key", "models", "is_active", "priority", "weight"}


async def update_channel(session: AsyncSession, channel_id: int, **kwargs) -> Optional[Channel]:
    result = await session.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if channel:
        # 只更新白名单中的字段
        for key, value in kwargs.items():
            if key in CHANNEL_UPDATE_FIELDS:
                setattr(channel, key, value)
        await session.commit()
        await session.refresh(channel)
        return channel
    return None


async def toggle_channel(session: AsyncSession, channel_id: int, is_active: bool) -> Optional[Channel]:
    """切换渠道启用/禁用状态"""
    result = await session.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if channel:
        channel.is_active = is_active
        await session.commit()
        await session.refresh(channel)
        return channel
    return None


async def delete_channel(session: AsyncSession, channel_id: int) -> bool:
    result = await session.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if channel:
        await session.delete(channel)
        await session.commit()
        return True
    return False


async def create_usage_log(session: AsyncSession, **kwargs) -> UsageLog:
    usage_log = UsageLog(**kwargs)
    session.add(usage_log)
    await session.commit()
    return usage_log


async def get_usage_logs(session: AsyncSession, api_key_id: Optional[int] = None,
                        start_time: Optional[datetime] = None, end_time: Optional[datetime] = None,
                        limit: int = 100) -> List[UsageLog]:
    query = select(UsageLog).order_by(UsageLog.timestamp.desc()).limit(limit)
    if api_key_id:
        query = query.where(UsageLog.api_key_id == api_key_id)
    if start_time:
        query = query.where(UsageLog.timestamp >= start_time)
    if end_time:
        query = query.where(UsageLog.timestamp <= end_time)
    result = await session.execute(query)
    return result.scalars().all()


async def get_usage_summary(session: AsyncSession, api_key_id: Optional[int] = None,
                           days: int = 7) -> dict:
    start_time = datetime.utcnow() - timedelta(days=days)
    query = select(UsageLog).where(UsageLog.timestamp >= start_time)
    if api_key_id:
        query = query.where(UsageLog.api_key_id == api_key_id)
    result = await session.execute(query)
    logs = result.scalars().all()

    total_requests = len(logs)
    total_request_tokens = sum(log.request_tokens for log in logs)
    total_response_tokens = sum(log.response_tokens for log in logs)
    total_cost = sum(log.cost for log in logs)

    return {
        "total_requests": total_requests,
        "total_request_tokens": total_request_tokens,
        "total_response_tokens": total_response_tokens,
        "total_tokens": total_request_tokens + total_response_tokens,
        "total_cost": total_cost,
        "days": days
    }


async def get_model_stats(session: AsyncSession, hours: int = 168) -> dict:
    """获取按模型分组的统计数据，支持小时级别"""
    from datetime import timedelta
    start_time = datetime.utcnow() - timedelta(hours=hours)
    query = select(UsageLog).where(UsageLog.timestamp >= start_time)
    result = await session.execute(query)
    logs = result.scalars().all()

    # 按模型分组统计
    model_stats = {}
    for log in logs:
        model = log.model
        if model not in model_stats:
            model_stats[model] = {
                "model": model,
                "requests": 0,
                "request_tokens": 0,
                "response_tokens": 0,
                "cost": 0.0,
            }
        model_stats[model]["requests"] += 1
        model_stats[model]["request_tokens"] += log.request_tokens
        model_stats[model]["response_tokens"] += log.response_tokens
        model_stats[model]["cost"] += log.cost

    # 按请求次数排序
    sorted_stats = sorted(model_stats.values(), key=lambda x: x["requests"], reverse=True)

    # 计算days/hours显示
    if hours < 24:
        period_label = f"{hours}h"
    else:
        period_label = f"{hours // 24}d"

    return {
        "stats": sorted_stats,
        "total_requests": len(logs),
        "total_tokens": sum(log.request_tokens + log.response_tokens for log in logs),
        "total_cost": sum(log.cost for log in logs),
        "period": period_label,
        "hours": hours
    }


# 模型价格管理
async def create_model_price(session: AsyncSession, model: str, input_price: float, output_price: float) -> ModelPrice:
    """创建模型价格配置"""
    price = ModelPrice(
        model=model,
        input_price=input_price,
        output_price=output_price
    )
    session.add(price)
    await session.commit()
    await session.refresh(price)
    return price


async def get_all_model_prices(session: AsyncSession) -> List[ModelPrice]:
    """获取所有模型价格配置"""
    result = await session.execute(select(ModelPrice).order_by(ModelPrice.model))
    return result.scalars().all()


async def get_model_price(session: AsyncSession, model: str) -> Optional[ModelPrice]:
    """获取特定模型的价格配置"""
    result = await session.execute(select(ModelPrice).where(ModelPrice.model == model, ModelPrice.is_active == True))
    return result.scalar_one_or_none()


async def get_model_price_by_id(session: AsyncSession, price_id: int) -> Optional[ModelPrice]:
    """通过ID获取价格配置"""
    result = await session.execute(select(ModelPrice).where(ModelPrice.id == price_id))
    return result.scalar_one_or_none()


# 模型价格可更新字段白名单
MODEL_PRICE_UPDATE_FIELDS = {"model", "input_price", "output_price", "is_active"}


async def update_model_price(session: AsyncSession, price_id: int, **kwargs) -> Optional[ModelPrice]:
    """更新模型价格配置"""
    result = await session.execute(select(ModelPrice).where(ModelPrice.id == price_id))
    price = result.scalar_one_or_none()
    if price:
        # 只更新白名单中的字段
        for key, value in kwargs.items():
            if key in MODEL_PRICE_UPDATE_FIELDS:
                setattr(price, key, value)
        await session.commit()
        await session.refresh(price)
        return price
    return None


async def toggle_model_price(session: AsyncSession, price_id: int, is_active: bool) -> Optional[ModelPrice]:
    """切换模型价格启用/禁用状态"""
    result = await session.execute(select(ModelPrice).where(ModelPrice.id == price_id))
    price = result.scalar_one_or_none()
    if price:
        price.is_active = is_active
        await session.commit()
        await session.refresh(price)
        return price
    return None


async def delete_model_price(session: AsyncSession, price_id: int) -> bool:
    """删除模型价格配置"""
    result = await session.execute(select(ModelPrice).where(ModelPrice.id == price_id))
    price = result.scalar_one_or_none()
    if price:
        await session.delete(price)
        await session.commit()
        return True
    return False