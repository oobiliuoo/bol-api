import random
import time
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.crud import get_active_channels, get_channel_by_id
from app.db.models import Channel
from app.providers.base import BaseProvider
from app.providers.openai import OpenAIProvider
from app.providers.anthropic import AnthropicProvider
from app.providers.custom import CustomProvider


class ChannelCache:
    """渠道列表缓存（带 TTL）"""
    _instance = None
    _channels: List[Channel] = []
    _cache_time: float = 0
    _ttl: int = 60  # 缓存有效期（秒）

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def get(cls) -> Tuple[Optional[List[Channel]], float]:
        """获取缓存和缓存时间"""
        instance = cls.get_instance()
        if instance._channels and (time.time() - instance._cache_time) < instance._ttl:
            return instance._channels, instance._cache_time
        return None, 0

    @classmethod
    def set(cls, channels: List[Channel]):
        """设置缓存"""
        instance = cls.get_instance()
        instance._channels = channels
        instance._cache_time = time.time()

    @classmethod
    def invalidate(cls):
        """使缓存失效"""
        instance = cls.get_instance()
        instance._channels = []
        instance._cache_time = 0


def create_provider(channel: Channel) -> BaseProvider:
    """根据渠道类型创建对应的Provider"""
    if channel.provider_type == "openai":
        return OpenAIProvider(
            base_url=channel.base_url,
            api_key=channel.api_key,
            models=channel.models or []
        )
    elif channel.provider_type == "anthropic":
        return AnthropicProvider(
            base_url=channel.base_url,
            api_key=channel.api_key,
            models=channel.models or []
        )
    else:  # custom
        return CustomProvider(
            base_url=channel.base_url,
            api_key=channel.api_key,
            models=channel.models or [],
            api_protocol=channel.api_protocol or "openai"
        )


class ChannelManager:
    """渠道管理器，负责选择合适的渠道并实现调度策略"""

    @staticmethod
    async def _get_cached_channels(session: AsyncSession) -> List[Channel]:
        """获取活跃渠道（优先使用缓存）"""
        cached, _ = ChannelCache.get()
        if cached is not None:
            return cached

        channels = await get_active_channels(session)
        ChannelCache.set(channels)
        return channels

    @staticmethod
    def _match_model(channel: Channel, model: str) -> bool:
        """检查渠道是否支持指定模型"""
        models = channel.models or []
        # 空列表表示支持所有模型
        if len(models) == 0:
            return True
        # 检查精确匹配或前缀匹配（如 gpt-4 匹配 gpt-4-*）
        for supported_model in models:
            if model == supported_model:
                return True
            # 支持通配符匹配：gpt-4 匹配 gpt-4-*
            if supported_model.endswith("*"):
                prefix = supported_model[:-1]
                if model.startswith(prefix):
                    return True
        return False

    @staticmethod
    def _select_by_weight(channels: List[Channel]) -> Channel:
        """根据权重随机选择渠道（加权随机）"""
        total_weight = sum(c.weight for c in channels)
        # 如果所有权重都是0或负数，随机选择一个
        if total_weight <= 0:
            return random.choice(channels)

        # 加权随机选择
        r = random.uniform(0, total_weight)
        cumulative = 0
        for channel in channels:
            cumulative += channel.weight
            if r <= cumulative:
                return channel
        return channels[-1]

    @staticmethod
    async def select_channel(session: AsyncSession, model: str, exclude_ids: List[int] = None) -> Optional[Channel]:
        """根据模型选择合适的渠道

        调度策略：
        1. 筛选支持该模型的活跃渠道
        2. 排除已失败的渠道（exclude_ids）
        3. 按优先级分组（高优先级优先）
        4. 在最高优先级组内按权重随机选择
        """
        exclude_ids = exclude_ids or []
        channels = await ChannelManager._get_cached_channels(session)

        # 筛选支持该模型且未被排除的渠道
        matching_channels = [
            c for c in channels
            if ChannelManager._match_model(c, model) and c.id not in exclude_ids
        ]

        if not matching_channels:
            return None

        # 按优先级分组
        priority_groups: dict[int, List[Channel]] = {}
        for channel in matching_channels:
            priority = channel.priority
            if priority not in priority_groups:
                priority_groups[priority] = []
            priority_groups[priority].append(channel)

        # 获取最高优先级组
        max_priority = max(priority_groups.keys())
        top_group = priority_groups[max_priority]

        # 在最高优先级组内按权重选择
        return ChannelManager._select_by_weight(top_group)

    @staticmethod
    async def select_all_channels(session: AsyncSession, model: str) -> List[Channel]:
        """获取所有支持该模型的渠道（用于fallback）

        返回按优先级降序排列的渠道列表
        """
        channels = await ChannelManager._get_cached_channels(session)
        matching_channels = [c for c in channels if ChannelManager._match_model(c, model)]
        # 按优先级降序排序
        matching_channels.sort(key=lambda c: c.priority, reverse=True)
        return matching_channels

    @staticmethod
    async def get_provider(session: AsyncSession, model: str) -> Optional[BaseProvider]:
        """获取指定模型的Provider"""
        channel = await ChannelManager.select_channel(session, model)
        if channel:
            return create_provider(channel)
        return None

    @staticmethod
    async def get_provider_by_channel_id(session: AsyncSession, channel_id: int) -> Optional[BaseProvider]:
        """根据渠道ID获取Provider"""
        channel = await get_channel_by_id(session, channel_id)
        if channel:
            return create_provider(channel)
        return None

    @staticmethod
    async def get_available_models(session: AsyncSession) -> List[str]:
        """获取所有可用模型列表"""
        channels = await get_active_channels(session)
        models = set()
        for channel in channels:
            channel_models = channel.models or []
            if len(channel_models) == 0:
                # 如果渠道支持所有模型，无法列出具体模型
                continue
            models.update(channel_models)
        return sorted(list(models))