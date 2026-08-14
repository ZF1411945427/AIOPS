"""域模型: model (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""

import json

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint

from app.database import Base


class PredictionModel(Base):
    __tablename__ = "prediction_models"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    metric_name = Column(String(64), nullable=False)
    asset_id = Column(Integer, nullable=True)
    model_type = Column(String(32), default="linear")
    model_params = Column(Text, default="{}")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class TraceAnomalyConfig(Base):
    __tablename__ = "trace_anomaly_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128))
    service_name = Column(String(128), default="")
    latency_threshold_ms = Column(Float, default=1000)
    error_rate_threshold = Column(Float, default=0.05)
    check_window_minutes = Column(Integer, default=30)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class ClusterAnomalyEvent(Base):
    __tablename__ = "cluster_anomaly_events"

    id = Column(Integer, primary_key=True, index=True)
    anomaly_type = Column(String(64))
    cluster = Column(String(128), default="default")
    message = Column(Text, default="")
    severity = Column(String(32), default="warning")
    count = Column(Integer, default=1)
    first_seen_at = Column(DateTime)
    last_seen_at = Column(DateTime)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now())
