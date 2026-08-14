"""域模型: data (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""

import json

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint

from app.database import Base


class CiModel(Base):
    __tablename__ = "ci_models"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, nullable=False)
    display_name = Column(String(128), default="")
    description = Column(Text, default="")
    parent_type = Column(String(64), nullable=True)
    icon = Column(String(32), default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


class CiAttribute(Base):
    __tablename__ = "ci_attributes"

    id = Column(Integer, primary_key=True, index=True)
    ci_model_id = Column(Integer, ForeignKey("ci_models.id"), nullable=False)
    name = Column(String(64), nullable=False)
    display_name = Column(String(128), default="")
    field_type = Column(String(32), default="string")
    is_required = Column(Boolean, default=False)
    default_value = Column(String(256), default="")
    attr_options = Column(Text, default="")
    order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())


class ExtCmdbConfig(Base):
    __tablename__ = "ext_cmdb_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128))
    cmdb_type = Column(String(32), default="generic")
    api_url = Column(String(512))
    auth_config = Column(Text, default="{}")
    sync_interval = Column(Integer, default=60)
    last_synced_at = Column(DateTime, nullable=True)
    enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now())


class KafkaPipeline(Base):
    __tablename__ = "kafka_pipelines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128))
    brokers = Column(String(512))
    topic = Column(String(128))
    group_id = Column(String(128), default="aiops")
    pipeline_type = Column(String(32), default="log")
    transform = Column(String(32), default="raw")
    enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now())


class ExtEventSource(Base):
    __tablename__ = "ext_event_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128))
    source_type = Column(String(32), default="zabbix")
    api_url = Column(String(512))
    auth_config = Column(Text, default="{}")
    sync_interval = Column(Integer, default=60)
    last_synced_at = Column(DateTime, nullable=True)
    enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now())


class NetFlowRecord(Base):
    __tablename__ = "netflow_records"

    id = Column(Integer, primary_key=True, index=True)
    src_ip = Column(String(64))
    dst_ip = Column(String(64))
    src_port = Column(Integer, default=0)
    dst_port = Column(Integer, default=0)
    protocol = Column(String(16), default="TCP")
    bytes_sent = Column(Integer, default=0)
    bytes_rcvd = Column(Integer, default=0)
    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now())


class NetFlowCollector(Base):
    __tablename__ = "netflow_collectors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128))
    collector_type = Column(String(32), default="sflow")
    listen_host = Column(String(64), default="0.0.0.0")
    listen_port = Column(Integer, default=6343)
    enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now())


class ServiceMeshConfig(Base):
    __tablename__ = "service_mesh_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128))
    mesh_type = Column(String(32), default="istio")
    api_url = Column(String(512), default="")
    auth_config = Column(Text, default="{}")
    enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now())


class FeatureStoreItem(Base):
    __tablename__ = "feature_store_items"

    id = Column(Integer, primary_key=True, index=True)
    feature_name = Column(String(128), index=True)
    entity_type = Column(String(64), default="asset")
    entity_id = Column(Integer, default=0)
    feature_value = Column(Float, default=0.0)
    feature_json = Column(Text, default="{}")
    source = Column(String(64), default="manual")
    created_at = Column(DateTime, default=lambda: datetime.now())
