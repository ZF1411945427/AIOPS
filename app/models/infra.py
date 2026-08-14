"""域模型: infra (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""

import json

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint

from app.database import Base


class K8sUpgradeJob(Base):
    """edge 升级任务协调器(F5) - 状态机/批次/回滚, 持久化可恢复。"""
    __tablename__ = "k8s_upgrade_jobs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    cluster_id = Column(Integer, nullable=True)
    from_version = Column(String(32), default="")
    to_version = Column(String(32), default="")
    status = Column(String(24), default="pending")  # pending/running/paused/completed/failed/rolled_back
    strategy = Column(String(16), default="batch")  # all_at_once / batch
    batch_size = Column(Integer, default=1)
    overall_progress = Column(Integer, default=0)
    log_json = Column(Text, default="[]")
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class GitRepo(Base):
    """代码/git 知识库同步(P2-5) - 记录已同步到本地的 git 仓库用于代码搜索。"""
    __tablename__ = "git_repos"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    url = Column(String(512), nullable=False)
    branch = Column(String(128), default="main")
    local_path = Column(String(512), default="")
    status = Column(String(16), default="pending")  # pending/cloning/ready/error
    file_count = Column(Integer, default=0)
    last_sync_at = Column(DateTime, nullable=True)
    error_msg = Column(Text, default="")
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class K8sUpgradeStep(Base):
    """升级步骤(F5) - 逐 agent 升级/verify/回滚。"""
    __tablename__ = "k8s_upgrade_steps"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, index=True)
    step_order = Column(Integer, default=0)
    batch_no = Column(Integer, default=0)
    agent_id = Column(String(64), default="")
    hostname = Column(String(128), default="")
    action = Column(String(16), default="upgrade")  # upgrade / verify / rollback
    status = Column(String(16), default="pending")  # pending/running/success/failed/skipped
    output = Column(Text, default="")
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())


class NetworkDevice(Base):
    """网络设备管理(F6) - SNMP 校验/接口轮询/邻居发现。"""
    __tablename__ = "network_devices"
    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, nullable=True)
    name = Column(String(128), nullable=False)
    ip = Column(String(64), nullable=False)
    device_type = Column(String(16), default="switch")  # switch/router/firewall/ap/other
    vendor = Column(String(64), default="")
    model = Column(String(128), default="")
    snmp_version = Column(String(8), default="v2c")
    community = Column(String(128), default="public")
    port = Column(Integer, default=161)
    status = Column(String(16), default="unreachable")  # unreachable / ok / error
    last_poll_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class NetworkInterface(Base):
    """网络设备接口(F6)。"""
    __tablename__ = "network_interfaces"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, index=True)
    if_index = Column(Integer, nullable=False)
    name = Column(String(64), default="")
    type = Column(Integer, default=6)  # ifType, 6=ethernetCsmacd
    mac = Column(String(32), default="")
    admin_status = Column(Integer, default=1)  # 1=up 2=down
    oper_status = Column(Integer, default=1)  # 1=up 2=down
    speed = Column(Integer, default=0)
    in_octets = Column(Float, default=0)
    out_octets = Column(Float, default=0)
    in_errors = Column(Float, default=0)
    out_errors = Column(Float, default=0)
    last_poll_at = Column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("device_id", "if_index", name="uq_net_if_device_index"),)


class NetworkNeighbor(Base):
    """网络设备邻居(F6, LLDP/CDP)。"""
    __tablename__ = "network_neighbors"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, index=True)
    local_interface = Column(String(64), default="")
    neighbor_device = Column(String(128), default="")
    neighbor_port = Column(String(64), default="")
    proto = Column(String(8), default="lldp")  # lldp / cdp
    last_seen_at = Column(DateTime, default=lambda: datetime.now())
