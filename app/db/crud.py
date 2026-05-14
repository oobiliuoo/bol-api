import secrets
import hashlib
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import APIKey, Channel, UsageLog, ModelPrice, SystemSetting
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Union
from app.utils.encryption import encrypt_key, decrypt_key, is_encrypted


async def create_api_key(
    session: AsyncSession, name: Optional[str] = None
) -> tuple[str, APIKey]:
    raw_key = f"bol-{secrets.token_urlsafe(28)}"  # 添加前缀便于识别
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12] + "..." + raw_key[-4:]  # 显示前12位和后4位
    encrypted_key = encrypt_key(raw_key)  # 加密存储
    api_key = APIKey(
        key_hash=key_hash, encrypted_key=encrypted_key, key_prefix=key_prefix, name=name
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


async def toggle_api_key(
    session: AsyncSession, key_id: int, is_active: bool
) -> Optional[APIKey]:
    result = await session.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()
    if api_key:
        api_key.is_active = is_active
        await session.commit()
        await session.refresh(api_key)
        return api_key
    return None


async def create_channel(
    session: AsyncSession,
    name: str,
    provider_type: str,
    base_url: str,
    api_key: str,
    models: List[str],
    priority: int = 1,
    weight: float = 1.0,
    api_protocol: str = "openai",
) -> Channel:
    from app.channels.manager import ChannelCache

    channel = Channel(
        name=name,
        provider_type=provider_type,
        api_protocol=api_protocol,
        base_url=base_url,
        api_key=api_key,
        models=models,
        priority=priority,
        weight=weight,
    )
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    ChannelCache.invalidate()  # 使缓存失效

    # 自动将渠道中的模型同步到价格列表，默认价格为 0
    await _sync_models_to_prices(session, models)

    return channel


async def get_all_channels(session: AsyncSession) -> List[Channel]:
    result = await session.execute(select(Channel).order_by(Channel.priority.desc()))
    return result.scalars().all()


async def get_active_channels(session: AsyncSession) -> List[Channel]:
    result = await session.execute(
        select(Channel)
        .where(Channel.is_active == True)
        .order_by(Channel.priority.desc())
    )
    return result.scalars().all()


async def get_channel_by_id(
    session: AsyncSession, channel_id: int
) -> Optional[Channel]:
    result = await session.execute(select(Channel).where(Channel.id == channel_id))
    return result.scalar_one_or_none()


# 渠道可更新字段白名单
CHANNEL_UPDATE_FIELDS = {
    "name",
    "provider_type",
    "api_protocol",
    "base_url",
    "api_key",
    "models",
    "is_active",
    "priority",
    "weight",
}


async def update_channel(
    session: AsyncSession, channel_id: int, **kwargs
) -> Optional[Channel]:
    from app.channels.manager import ChannelCache

    result = await session.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if channel:
        # 只更新白名单中的字段
        for key, value in kwargs.items():
            if key in CHANNEL_UPDATE_FIELDS:
                setattr(channel, key, value)
        await session.commit()
        await session.refresh(channel)
        ChannelCache.invalidate()  # 使缓存失效

        # 如果更新了模型列表，自动同步新模型到价格列表
        if "models" in kwargs and kwargs["models"]:
            await _sync_models_to_prices(session, kwargs["models"])

        return channel
    return None


async def toggle_channel(
    session: AsyncSession, channel_id: int, is_active: bool
) -> Optional[Channel]:
    """切换渠道启用/禁用状态"""
    from app.channels.manager import ChannelCache

    result = await session.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if channel:
        channel.is_active = is_active
        await session.commit()
        await session.refresh(channel)
        ChannelCache.invalidate()  # 使缓存失效
        return channel
    return None


async def delete_channel(session: AsyncSession, channel_id: int) -> bool:
    from app.channels.manager import ChannelCache

    result = await session.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if channel:
        await session.delete(channel)
        await session.commit()
        ChannelCache.invalidate()  # 使缓存失效
        return True
    return False


async def create_usage_log(session: AsyncSession, **kwargs) -> UsageLog:
    usage_log = UsageLog(**kwargs)
    session.add(usage_log)
    await session.commit()
    return usage_log


async def get_usage_logs(
    session: AsyncSession,
    api_key_id: Optional[int] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
    return_count: bool = False,
    return_summary: bool = False,
    model_filter: Optional[str] = None,
    status_code_filter: Optional[int] = None,
) -> Union[List[UsageLog], tuple]:
    """获取用量日志，支持分页、筛选和统计"""
    # 构建基础查询条件
    conditions = []
    if api_key_id:
        conditions.append(UsageLog.api_key_id == api_key_id)
    if start_time:
        conditions.append(UsageLog.timestamp >= start_time)
    if end_time:
        conditions.append(UsageLog.timestamp <= end_time)
    if model_filter:
        conditions.append(UsageLog.model == model_filter)
    if status_code_filter is not None:
        if status_code_filter == -1:  # 错误状态（非 200 和非 499）
            conditions.append(UsageLog.status_code != 200)
            conditions.append(UsageLog.status_code != 499)
        else:
            conditions.append(UsageLog.status_code == status_code_filter)

    # 主查询
    query = select(UsageLog).order_by(UsageLog.timestamp.desc()).limit(limit).offset(offset)
    for cond in conditions:
        query = query.where(cond)
    result = await session.execute(query)
    logs = result.scalars().all()

    if return_count or return_summary:
        count_query = select(func.count()).select_from(UsageLog)
        for cond in conditions:
            count_query = count_query.where(cond)
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        if return_summary:
            # 汇总统计
            sum_query = select(
                func.sum(UsageLog.request_tokens).label("total_input"),
                func.sum(UsageLog.response_tokens).label("total_output"),
                func.sum(UsageLog.cost).label("total_cost"),
                func.avg(UsageLog.latency_ms).label("avg_latency"),
            )
            for cond in conditions:
                sum_query = sum_query.where(cond)
            sum_result = await session.execute(sum_query)
            sum_row = sum_result.one()

            # 状态码分布
            status_query = select(
                UsageLog.status_code,
                func.count().label("count")
            )
            for cond in conditions:
                status_query = status_query.where(cond)
            status_query = status_query.group_by(UsageLog.status_code)
            status_result = await session.execute(status_query)
            status_dist = {row.status_code: row.count for row in status_result}

            summary = {
                "total_requests": total,
                "total_input": sum_row.total_input or 0,
                "total_output": sum_row.total_output or 0,
                "total_cost": sum_row.total_cost or 0.0,
                "avg_latency": int(sum_row.avg_latency or 0),
                "success_count": status_dist.get(200, 0),
                "cancelled_count": status_dist.get(499, 0),
                "error_count": total - status_dist.get(200, 0) - status_dist.get(499, 0),
            }
            return logs, total, summary

        return logs, total
    return logs


async def get_usage_summary(
    session: AsyncSession, api_key_id: Optional[int] = None, days: int = 7
) -> dict:
    """获取用量统计摘要（全量汇总，不受 days 参数限制）"""
    # 全量统计
    query = select(
        func.count().label("total_requests"),
        func.sum(UsageLog.request_tokens).label("total_request_tokens"),
        func.sum(UsageLog.response_tokens).label("total_response_tokens"),
        func.sum(UsageLog.cost).label("total_cost"),
    )

    if api_key_id:
        query = query.where(UsageLog.api_key_id == api_key_id)

    result = await session.execute(query)
    row = result.one()

    total_request_tokens = row.total_request_tokens or 0
    total_response_tokens = row.total_response_tokens or 0
    total_tokens = total_request_tokens + total_response_tokens

    # 全量时间跨度（用于追踪天数和 RPM/TPM 计算）
    time_query = select(
        func.min(UsageLog.timestamp).label("first_time"),
        func.max(UsageLog.timestamp).label("last_time"),
    )
    if api_key_id:
        time_query = time_query.where(UsageLog.api_key_id == api_key_id)

    time_result = await session.execute(time_query)
    time_row = time_result.one()

    if time_row.first_time and time_row.last_time:
        delta = time_row.last_time - time_row.first_time
        active_minutes = max(1, int(delta.total_seconds() / 60))
        actual_days = max(1, round(delta.total_seconds() / 86400))
    else:
        active_minutes = days * 24 * 60
        actual_days = days

    return {
        "total_requests": row.total_requests or 0,
        "total_request_tokens": total_request_tokens,
        "total_response_tokens": total_response_tokens,
        "total_tokens": total_tokens,
        "total_cost": row.total_cost or 0.0,
        "days": actual_days,
        "rpm": round((row.total_requests or 0) / active_minutes, 2)
        if active_minutes > 0
        else 0.0,
        "tpm": round(total_tokens / active_minutes, 2) if active_minutes > 0 else 0.0,
    }


def _calc_start_time(period: str) -> tuple[datetime, str]:
    """根据日历周期计算起始时间和显示标签

    Args:
        period: "today", "week", "month"

    Returns:
        (start_time, label)
    """
    now = datetime.now(timezone.utc)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        label = "本日"
    elif period == "week":
        # 本周一 00:00 UTC
        days_since_monday = now.weekday()
        start = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        label = "本周"
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        label = "本月"
    else:
        raise ValueError(f"Unknown period: {period}")
    return start, label


async def get_model_stats(
    session: AsyncSession, hours: int = 168, period: str = None,
    start_time: datetime = None, end_time: datetime = None
) -> dict:
    """获取按模型分组的统计数据（p50 延迟 + 峰值延迟）

    优先级：start_time/end_time > period > hours
    """
    if start_time:
        end = end_time or datetime.now(timezone.utc)
        span_hours = (end - start_time).total_seconds() / 3600
        period_label = "自定义"
    elif period:
        start_time, period_label = _calc_start_time(period)
        end = datetime.now(timezone.utc)
    else:
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        end = datetime.now(timezone.utc)
        if hours < 24:
            period_label = f"{hours}h"
        else:
            period_label = f"{hours // 24}d"

    # 构建时间过滤条件
    time_conditions = [UsageLog.timestamp >= start_time]
    if end_time:
        time_conditions.append(UsageLog.timestamp <= end_time)

    # 1. 主聚合查询
    query = (
        select(
            UsageLog.model,
            func.count().label("requests"),
            func.sum(UsageLog.request_tokens).label("request_tokens"),
            func.sum(UsageLog.response_tokens).label("response_tokens"),
            func.sum(UsageLog.cost).label("cost"),
        )
        .where(*time_conditions)
        .group_by(UsageLog.model)
    )

    result = await session.execute(query)
    rows = result.all()

    # 2. 获取所有延迟值
    latency_query = select(UsageLog.model, UsageLog.latency_ms).where(
        UsageLog.latency_ms > 0, *time_conditions
    )
    latency_result = await session.execute(latency_query)

    latency_map = {}
    for row in latency_result:
        latency_map.setdefault(row.model, []).append(row.latency_ms)

    # 3. 获取状态码分布
    status_query = (
        select(
            UsageLog.model,
            UsageLog.status_code,
            func.count().label("count")
        )
        .where(*time_conditions)
        .group_by(UsageLog.model, UsageLog.status_code)
    )
    status_result = await session.execute(status_query)

    status_map = {}  # model -> {status_code: count}
    for row in status_result:
        if row.model not in status_map:
            status_map[row.model] = {}
        status_map[row.model][row.status_code] = row.count

    # 4. 按模型计算 p50 和峰值
    latency_stats = {}
    for model, lats in latency_map.items():
        lats.sort()
        mid = len(lats) // 2
        p50 = lats[mid]  # 偶数长度取上中位数
        peak = lats[-1]
        latency_stats[model] = {"p50": p50, "peak": peak}

    # 5. 合并结果
    model_stats = []
    total_requests = 0
    total_tokens = 0
    total_cost = 0.0
    total_errors = 0

    for row in rows:
        req_tokens = row.request_tokens or 0
        resp_tokens = row.response_tokens or 0
        cost = row.cost or 0.0

        ls = latency_stats.get(row.model, {"p50": 0, "peak": 0})

        # 计算错误数和错误率
        model_status = status_map.get(row.model, {})
        error_count = sum(c for code, c in model_status.items() if code != 200)
        error_rate = round(error_count / row.requests * 100, 1) if row.requests > 0 else 0.0

        model_stats.append(
            {
                "model": row.model,
                "requests": row.requests,
                "request_tokens": req_tokens,
                "response_tokens": resp_tokens,
                "cost": cost,
                "p50_latency": ls["p50"],
                "peak_latency": ls["peak"],
                "error_count": error_count,
                "error_rate": error_rate,
            }
        )

        total_requests += row.requests
        total_tokens += req_tokens + resp_tokens
        total_cost += cost
        total_errors += error_count

    # 按请求次数排序
    model_stats.sort(key=lambda x: x["requests"], reverse=True)

    # 计算总体 p50 和峰值
    all_latencies = []
    for lats in latency_map.values():
        all_latencies.extend(lats)
    all_latencies.sort()
    total_p50 = all_latencies[len(all_latencies) // 2] if all_latencies else 0
    total_peak = all_latencies[-1] if all_latencies else 0

    # 总体错误率
    total_error_rate = round(total_errors / total_requests * 100, 1) if total_requests > 0 else 0.0

    return {
        "stats": model_stats,
        "total_requests": total_requests,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "total_p50": total_p50,
        "total_peak": total_peak,
        "total_errors": total_errors,
        "total_error_rate": total_error_rate,
        "period": period_label,
        "hours": hours,
    }


# 模型价格管理
async def create_model_price(
    session: AsyncSession, model: str, input_price: float, output_price: float
) -> ModelPrice:
    """创建模型价格配置"""
    price = ModelPrice(model=model, input_price=input_price, output_price=output_price)
    session.add(price)
    await session.commit()
    await session.refresh(price)
    return price


async def _sync_models_to_prices(session: AsyncSession, models: List[str]):
    """将渠道中的模型自动同步到价格列表，已存在的跳过"""
    from sqlalchemy import select

    for model in models:
        result = await session.execute(
            select(ModelPrice).where(ModelPrice.model == model)
        )
        if not result.scalar_one_or_none():
            session.add(ModelPrice(model=model, input_price=0.0, output_price=0.0))
    if models:
        await session.commit()


async def get_all_model_prices(session: AsyncSession) -> List[ModelPrice]:
    """获取所有模型价格配置"""
    result = await session.execute(select(ModelPrice).order_by(ModelPrice.model))
    return result.scalars().all()


async def get_model_price(session: AsyncSession, model: str) -> Optional[ModelPrice]:
    """获取特定模型的价格配置"""
    result = await session.execute(
        select(ModelPrice).where(
            ModelPrice.model == model, ModelPrice.is_active == True
        )
    )
    return result.scalar_one_or_none()


async def get_model_price_by_id(
    session: AsyncSession, price_id: int
) -> Optional[ModelPrice]:
    """通过ID获取价格配置"""
    result = await session.execute(select(ModelPrice).where(ModelPrice.id == price_id))
    return result.scalar_one_or_none()


# 模型价格可更新字段白名单
MODEL_PRICE_UPDATE_FIELDS = {"model", "input_price", "output_price", "is_active"}


async def update_model_price(
    session: AsyncSession, price_id: int, **kwargs
) -> Optional[ModelPrice]:
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


async def toggle_model_price(
    session: AsyncSession, price_id: int, is_active: bool
) -> Optional[ModelPrice]:
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


# 系统设置管理
async def get_setting(session: AsyncSession, key: str) -> Optional[str]:
    """获取配置值，不存在返回 None"""
    result = await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else None


async def set_setting(session: AsyncSession, key: str, value: str) -> SystemSetting:
    """创建或更新配置"""
    result = await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        setting = SystemSetting(key=key, value=value)
        session.add(setting)
    await session.commit()
    await session.refresh(setting)
    return setting


async def get_all_settings(session: AsyncSession) -> dict:
    """获取所有配置"""
    result = await session.execute(select(SystemSetting))
    return {s.key: s.value for s in result.scalars().all()}


async def get_trend_data(
    session: AsyncSession, hours: int = 168, period: str = None,
    start_time: datetime = None, end_time: datetime = None
) -> dict:
    """获取按时间桶 + 模型分组的趋势数据

    优先级：start_time/end_time > period > hours
    颗粒度：自定义范围按小时/天取决于跨度
    """
    if start_time:
        end = end_time or datetime.now(timezone.utc)
        span_hours = (end - start_time).total_seconds() / 3600
        hours = round(span_hours)  # 用实际跨度覆盖 hours 参数
        if span_hours <= 24:
            time_format = "%Y-%m-%dT%H:00:00"
            granularity = "hour"
        else:
            time_format = "%Y-%m-%dT00:00:00"
            granularity = "day"
    elif period:
        start_time, _ = _calc_start_time(period)
        if period == "today":
            granularity = "hour"
            time_format = "%Y-%m-%dT%H:00:00"
        else:
            granularity = "day"
            time_format = "%Y-%m-%dT00:00:00"
    else:
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        if hours <= 24:
            time_format = "%Y-%m-%dT%H:00:00"
            granularity = "hour"
        else:
            time_format = "%Y-%m-%dT00:00:00"
            granularity = "day"

    time_bucket_col = func.strftime(time_format, UsageLog.timestamp).label("time_bucket")

    # 按时间桶 + 模型分组聚合
    query = select(
        time_bucket_col,
        UsageLog.model,
        func.count().label("requests"),
        func.sum(func.coalesce(UsageLog.request_tokens, 0) + func.coalesce(UsageLog.response_tokens, 0)).label("tokens"),
        func.sum(UsageLog.cost).label("cost"),
    ).where(
        UsageLog.timestamp >= start_time
    ).group_by(
        time_bucket_col, UsageLog.model
    ).order_by(
        time_bucket_col
    )

    if end_time:
        query = query.where(UsageLog.timestamp <= end_time)

    result = await session.execute(query)
    rows = result.all()

    # 将扁平结果重构为按 model 分组的 series
    model_data = {}  # model -> list of data points
    for row in rows:
        if row.model not in model_data:
            model_data[row.model] = []
        model_data[row.model].append({
            "time": row.time_bucket + "Z",
            "requests": row.requests or 0,
            "tokens": row.tokens or 0,
            "cost": round(row.cost or 0.0, 6),
        })

    # 按总请求数排序，取 Top 8
    model_totals = [(m, sum(d["requests"] for d in data)) for m, data in model_data.items()]
    model_totals.sort(key=lambda x: x[1], reverse=True)
    top_models = [m for m, _ in model_totals[:8]]

    # 构建 series：Top 8 单独，其余合并为"其他"
    series = []
    for model in top_models:
        series.append({
            "model": model,
            "data": model_data[model],
        })

    # 合并其他模型
    other_data = {}
    for model, data in model_data.items():
        if model not in top_models:
            for dp in data:
                t = dp["time"]
                if t not in other_data:
                    other_data[t] = {"time": t, "requests": 0, "tokens": 0, "cost": 0.0}
                other_data[t]["requests"] += dp["requests"]
                other_data[t]["tokens"] += dp["tokens"]
                other_data[t]["cost"] += dp["cost"]

    if other_data:
        other_list = sorted(other_data.values(), key=lambda x: x["time"])
        series.append({"model": "其他", "data": other_list})

    return {
        "granularity": granularity,
        "hours": hours,
        "series": series,
    }
