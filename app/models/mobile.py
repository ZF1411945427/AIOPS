"""域模型: mobile (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""

import json

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint

from app.database import Base


class MobileDevice(Base):
    """移动端设备注册（绑定用户+设备，存推送 token 与生物识别 token）"""
    __tablename__ = "mobile_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id = Column(String(128), nullable=False)
    platform = Column(String(16), nullable=False)
    push_token = Column(String(256))
    biometric_token = Column(String(512))
    app_version = Column(String(32))
    last_active_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "device_id", name="uq_user_device"),)


class PushRecord(Base):
    """推送记录（审计 + 重试依据）"""
    __tablename__ = "push_records"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("mobile_devices.id"), nullable=False)
    title = Column(String(128), nullable=False)
    body = Column(Text)
    payload = Column(Text)
    type = Column(String(32))
    ref_id = Column(Integer)
    status = Column(String(16), default="pending")
    provider_msg_id = Column(String(128))
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime)
