"""域模型: metric (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""


from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text

from app.database import Base


class HotSpotAnalysis(Base):
    __tablename__ = "hotspot_analyses"

    id = Column(Integer, primary_key=True, index=True)
    metric_name = Column(String(64), nullable=False)
    dimension = Column(String(64), default="")
    dimension_value = Column(String(128), default="")
    contribution = Column(Float, default=0.0)
    baseline = Column(Float, default=0.0)
    current = Column(Float, default=0.0)
    change_pct = Column(Float, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now())


class MetricRecord(Base):
    __tablename__ = "metric_records"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True, default=None)
    name = Column(String(64), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(32), default="%")
    labels = Column(Text, default="{}")
    timestamp = Column(DateTime, default=lambda: datetime.now())


class MetricDashboardCard(Base):
    __tablename__ = "metric_dashboard_cards"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, default=0)
    title = Column(String(128), nullable=False)
    promql = Column(String(512), nullable=False)
    hours = Column(Integer, default=24)
    w = Column(Integer, default=2)
    h = Column(Integer, default=1)
    order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())


class MetricTemplate(Base):
    __tablename__ = "metric_templates"

    id = Column(Integer, primary_key=True, index=True)
    ci_type = Column(String(32), nullable=False, index=True)
    metric_key = Column(String(64), nullable=False)
    metric_name = Column(String(128), nullable=False)
    category = Column(String(32), default="performance")
    unit = Column(String(32), default="")
    description = Column(String(256), default="")
    collect_method = Column(String(32), default="ssh")
    collect_command = Column(String(512), default="")
    default_threshold_warn = Column(Float, nullable=True)
    default_threshold_critical = Column(Float, nullable=True)
    sort_order = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class AssetMetricRecommendation(Base):
    __tablename__ = "asset_metric_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    metric_key = Column(String(64), nullable=False)
    metric_name = Column(String(128), default="")
    category = Column(String(32), default="")
    unit = Column(String(32), default="")
    source = Column(String(16), default="template")
    status = Column(String(16), default="recommended")
    reason = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
