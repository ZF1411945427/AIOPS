"""域模型: deliver (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""


from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text

from app.database import Base


class ScriptTask(Base):
    __tablename__ = "script_tasks"

    id = Column(Integer, primary_key=True, index=True)
    target_name = Column(String(128))
    script_content = Column(Text)
    output = Column(Text, default="")
    error = Column(Text, default="")
    exit_code = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())


class Span(Base):
    __tablename__ = "spans"

    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(String(64), index=True)
    span_id = Column(String(64))
    parent_span_id = Column(String(64), default="")
    service_name = Column(String(128))
    operation_name = Column(String(256))
    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    duration_ms = Column(Float, default=0)
    status = Column(String(32), default="OK")
    tags = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now())


class BlueGreenDeploy(Base):
    __tablename__ = "blue_green_deploys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128))
    namespace = Column(String(64), default="default")
    cluster = Column(String(128), default="")
    active_label = Column(String(64), default="blue")
    standby_label = Column(String(64), default="green")
    active_replicas = Column(Integer, default=3)
    standby_replicas = Column(Integer, default=3)
    status = Column(String(32), default="active")
    last_switched_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class BlueGreenSwitchRecord(Base):
    __tablename__ = "blue_green_switch_records"

    id = Column(Integer, primary_key=True, index=True)
    deploy_id = Column(Integer, ForeignKey("blue_green_deploys.id"), nullable=False)
    from_label = Column(String(64), default="")
    to_label = Column(String(64), default="")
    operator = Column(String(64), default="system")
    description = Column(String(256), default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


class AnsibleInventory(Base):
    """Ansible 主机清单（YAML 格式）"""
    __tablename__ = "ansible_inventories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    description = Column(String(256), default="")
    content = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class AnsiblePlaybook(Base):
    """Ansible Playbook 模板（YAML 格式）"""
    __tablename__ = "ansible_playbooks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    description = Column(String(256), default="")
    content = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class AnsibleRun(Base):
    """Ansible 执行历史记录"""
    __tablename__ = "ansible_runs"

    id = Column(Integer, primary_key=True, index=True)
    inventory_id = Column(Integer, nullable=True)
    playbook_id = Column(Integer, nullable=True)
    inventory_name = Column(String(128), default="")
    playbook_name = Column(String(128), default="")
    extra_vars = Column(Text, default="")
    output = Column(Text, default="")
    error = Column(Text, default="")
    exit_code = Column(Integer, default=0)
    status = Column(String(32), default="pending")
    created_at = Column(DateTime, default=lambda: datetime.now())
    finished_at = Column(DateTime, nullable=True)


class OfflineRepoBundle(Base):
    """离线仓库包 - 对标 Pixiu builder 的离线包管理"""
    __tablename__ = "offline_repo_bundles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    version = Column(String(64), default="")
    os_type = Column(String(32), default="")
    os_version = Column(String(32), default="")
    bundle_type = Column(String(32), nullable=False, default="images")
    file_path = Column(String(512), default="")
    file_size = Column(Integer, default=0)
    md5 = Column(String(64), default="")
    status = Column(String(32), default="pending")
    loaded_images = Column(Integer, default=0)
    total_images = Column(Integer, default=0)
    loaded_packages = Column(Integer, default=0)
    load_message = Column(String(512), default="")
    loaded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class OfflineRegistry(Base):
    """私有镜像仓库配置 - 对标 Pixiu builder 的 Registry"""
    __tablename__ = "offline_registries"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    registry_url = Column(String(256), nullable=False)
    is_internal = Column(Boolean, default=False)
    storage_path = Column(String(512), default="")
    is_secure = Column(Boolean, default=False)
    username = Column(String(64), default="")
    password = Column(String(128), default="")
    has_password = Column(Boolean, default=False)
    is_default = Column(Boolean, default=False)
    status = Column(String(32), default="active")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class OfflinePackageSource(Base):
    """离线系统包源 - 对标 Pixiu builder 的 Apt/Yum 源"""
    __tablename__ = "offline_package_sources"

    id = Column(Integer, primary_key=True, index=True)
    bundle_id = Column(Integer, ForeignKey("offline_repo_bundles.id"), nullable=True)
    os_type = Column(String(32), nullable=False)
    os_version = Column(String(32), default="")
    source_url = Column(String(256), nullable=False)
    source_type = Column(String(16), nullable=False)
    package_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class DeployProxy(Base):
    """部署代理配置 - 在离线仓库页维护, 三个部署页下拉复用(仅供部署访问公网, 非仓库本身)。
    契约见 CONTRACT.md。"""
    __tablename__ = "deploy_proxies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    http_proxy = Column(String(256), default="")
    https_proxy = Column(String(256), default="")
    no_proxy = Column(String(512), default="")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
