"""域模型: dash (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""


from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text

from app.database import Base


class DashboardCardConfig(Base):
    __tablename__ = "dashboard_card_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    card_type = Column(String(64), nullable=False)
    title = Column(String(128), default="")
    card_config = Column(Text, default="{}")
    position = Column(Integer, default=0)
    is_visible = Column(Boolean, default=True)


class DashboardLayout(Base):
    __tablename__ = "dashboard_layouts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    layout_config = Column(Text, default="[]")
    is_default = Column(Boolean, default=False)
    is_shared = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
