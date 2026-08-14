"""域模型: asset (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""


from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text

from app.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    ci_type = Column(String(32), default="server")
    parent_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    ip = Column(String(64), default="")
    status = Column(String(32), default="offline")
    tags = Column(String(256), default="")
    ci_attributes = Column(Text, default="{}")
    k8s_cluster = Column(String(128), default="")
    connection_type = Column(String(32), default="ssh")
    connection_config = Column(Text, default="{}")
    edge_agent_id = Column(String(64), default="", index=True)  # P2: 关联 EdgeSession.agent_id，空=未纳管
    created_at = Column(DateTime, default=lambda: datetime.now())
    last_checked_at = Column(DateTime, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    health_status = Column(String(16), default="green")


class TagCategory(Base):
    __tablename__ = "tag_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False, unique=True)
    label = Column(String(64), nullable=False)
    color = Column(String(16), default="#6366f1")
    icon = Column(String(32), default="🏷️")
    sort_order = Column(Integer, default=0)


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    category_id = Column(Integer, ForeignKey("tag_categories.id"), nullable=True)
    color = Column(String(16), default="#6366f1")
    description = Column(String(256), default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


class AssetRelation(Base):
    __tablename__ = "asset_relations"

    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    child_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    relation_type = Column(String(32), default="depends_on")


class DataSource(Base):
    __tablename__ = "data_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    type = Column(String(32), nullable=False)
    endpoint = Column(String(512), default="")
    auth_type = Column(String(32), default="none")
    auth_config = Column(Text, default="")
    scrape_interval = Column(Integer, default=30)
    mapping_config = Column(Text, default="{}")
    enabled = Column(Boolean, default=True)
    last_status = Column(String(32), default="unknown")
    last_error = Column(Text, default="")
    last_scraped_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class AssetChangeLog(Base):
    __tablename__ = "asset_change_logs"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    asset_name = Column(String(256), default="")
    field = Column(String(64), default="")
    old_value = Column(Text, default="")
    new_value = Column(Text, default="")
    operator = Column(String(64), default="system")
    created_at = Column(DateTime, default=lambda: datetime.now())


class AssetSessionLink(Base):
    """资产与 AI 会话的关联"""
    __tablename__ = "asset_session_links"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    context_summary = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


class SavedFilter(Base):
    __tablename__ = "saved_filters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    page = Column(String(64), default="alerts")
    filters = Column(Text, default="{}")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class AssetLifecycle(Base):
    __tablename__ = "asset_lifecycles"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    status = Column(String(32), default="provisioning")
    previous_status = Column(String(32), default="")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
