"""域模型: system (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""

import json

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint

from app.database import Base


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    config_value = Column(Text, default="")
    description = Column(String(256), default="")
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class SystemPostureRecord(Base):
    """系统态势 SLA 每日快照"""
    __tablename__ = "system_posture_records"

    id = Column(Integer, primary_key=True, index=True)
    day = Column(String(16), nullable=False, index=True)
    system_key = Column(String(64), nullable=False)
    system_name = Column(String(128), default="")
    environment = Column(String(32), default="prod")
    domain = Column(String(64), default="")
    status = Column(String(16), default="unknown")
    sla_value = Column(Float, nullable=True)
    health_score = Column(Integer, nullable=True)
    alerts_count = Column(Integer, default=0)
    incidents_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())
