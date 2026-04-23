from sqlalchemy import Column, Integer, String, Boolean, Float, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    encrypted_key = Column(String(255), nullable=True)  # 加密存储的原始key
    key_prefix = Column(String(12), nullable=True)  # key前缀用于显示（如 "sk-abc..."）
    name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    rate_limit = Column(Integer, nullable=True)  # 每分钟请求限制

    usage_logs = relationship("UsageLog", back_populates="api_key")


class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    provider_type = Column(String(20), nullable=False)  # openai, anthropic, custom
    api_protocol = Column(String(20), default="openai")  # openai, anthropic - API请求格式
    base_url = Column(String(255), nullable=False)
    api_key = Column(String(255), nullable=False)  # 加密存储
    models = Column(JSON, default=list)  # 支持的模型列表
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=1)  # 优先级
    weight = Column(Float, default=1.0)  # 权重

    usage_logs = relationship("UsageLog", back_populates="channel")


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), nullable=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=True)
    provider = Column(String(20), nullable=False)
    model = Column(String(50), nullable=False)
    request_tokens = Column(Integer, default=0)
    response_tokens = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    endpoint = Column(String(100), nullable=False)
    status_code = Column(Integer, default=200)
    latency_ms = Column(Integer, default=0)

    api_key = relationship("APIKey", back_populates="usage_logs")
    channel = relationship("Channel", back_populates="usage_logs")