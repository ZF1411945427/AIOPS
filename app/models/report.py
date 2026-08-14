"""域模型: report (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""

import json

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint

from app.database import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    type = Column(String(32), nullable=False)
    period_started_at = Column(DateTime, nullable=True)
    period_ended_at = Column(DateTime, nullable=True)
    summary = Column(Text, default="")
    report_data = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


class ReportSchedule(Base):
    __tablename__ = "report_schedules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    report_type = Column(String(32), default="daily")
    cron_expr = Column(String(128), default="0 8 * * *")
    channel = Column(String(32), default="email")
    channel_config = Column(Text, default="{}")
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
