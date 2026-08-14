"""域模型: k8s (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""


from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text

from app.database import Base


class K8sEvent(Base):
    __tablename__ = "k8s_events"

    id = Column(Integer, primary_key=True, index=True)
    cluster = Column(String(128), default="")
    namespace = Column(String(128), default="")
    name = Column(String(256), default="")
    kind = Column(String(64), default="")
    reason = Column(String(128), default="")
    message = Column(Text, default="")
    source = Column(String(128), default="")
    first_seen_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    count = Column(Integer, default=1)
    severity = Column(String(32), default="info")
    created_at = Column(DateTime, default=lambda: datetime.now())


class DeployPlan(Base):
    """AI 自动部署计划（契约见 CONTRACT.md 第十一章）"""
    __tablename__ = "deploy_plans"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    artifact_path = Column(String(512), default="")
    artifact_download_path = Column(String(512), default="")
    artifact_auto_download = Column(Boolean, default=True)
    doc_raw = Column(Text, default="")
    doc_file_name = Column(String(256), default="")
    asset_ids = Column(Text, default="[]")
    env_mapping = Column(Text, default="{}")
    environment_probe_json = Column(Text, default="{}")  # SSH 环境探查结果
    env_analysis_json = Column(Text, default="{}")  # AI 环境分析→SOP 适配建议
    sop_json = Column(Text, default="[]")
    status = Column(String(32), default="draft")
    preflight_json = Column(Text, default="{}")
    deploy_report_json = Column(Text, default="{}")  # 部署报告（AI 生成）
    test_results_json = Column(Text, default="{}")  # 部署后验证/测试记录
    execution_history_json = Column(Text, default="[]")  # 执行历史记录
    cleanup_history_json = Column(Text, default="[]")  # 回滚清理历史记录
    last_deployed_at = Column(DateTime, nullable=True)
    deploy_count = Column(Integer, default=0)
    dag_json = Column(Text, default="{}")  # AI 执行引擎 DAG 执行计划
    ai_decision_log_json = Column(Text, default="[]")  # AI 自主决策日志
    strategy = Column(String(32), default="auto")  # AI 选定的部署策略: auto/rolling/blue-green/canary/recreate
    risk_score = Column(Integer, default=0)  # AI 预判的部署风险评分 0-100
    deployment_feature_json = Column(Text, default="{}")  # 部署特征向量(供 L5 学习)
    health_gate_json = Column(Text, default="[]")  # 部署过程中的健康门控记录
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class DeployStep(Base):
    """AI 自动部署步骤（契约见 CONTRACT.md 第十一章）"""
    __tablename__ = "deploy_steps"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("deploy_plans.id"), nullable=False)
    step_order = Column(Integer, default=0)
    description = Column(String(512), default="")
    command = Column(Text, default="")
    verify_command = Column(Text, default="")
    rollback_command = Column(Text, default="")
    risk_level = Column(String(16), default="medium")
    status = Column(String(32), default="pending")
    output = Column(Text, default="")
    diagnosis = Column(Text, default="")  # AI 失败诊断
    fix_command = Column(Text, default="")  # AI 建议修复命令
    retry_count = Column(Integer, default=0)
    precheck_result = Column(Text, default="")  # AI 预执行风险检查结果
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class K8sClusterPlan(Base):
    """K8S 离线集群部署计划"""
    __tablename__ = "k8s_cluster_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    kubernetes_version = Column(String(64), default="")
    runtime = Column(String(32), default="containerd")
    cni = Column(String(32), default="calico")
    pod_cidr = Column(String(32), default="10.244.0.0/16")
    service_cidr = Column(String(32), default="10.96.0.0/12")
    image_repository = Column(String(256), default="")
    bundle_id = Column(Integer, ForeignKey("offline_repo_bundles.id"), nullable=True)
    registry_id = Column(Integer, ForeignKey("offline_registries.id"), nullable=True)
    http_proxy = Column(String(256), default="")  # 在线部署代理（如 http://192.168.100.2:7897）
    https_proxy = Column(String(256), default="")  # 同上，HTTPS 用
    no_proxy = Column(String(512), default="127.0.0.1,localhost,.local")  # 不走代理的地址
    nodes_json = Column(Text, default="[]")  # 节点定义（见 CONTRACT 13.3）
    status = Column(String(32), default="draft")
    current_step = Column(Integer, default=0)
    logs_json = Column(Text, default="[]")  # 执行日志事件列表
    kubeconfig = Column(Text, default="")  # 敏感：产出 kubeconfig
    join_token = Column(Text, default="")  # 敏感：worker 加入 token（临时）
    report_json = Column(Text, default="{}")  # 部署报告
    untaint_master = Column(Boolean, default=False)  # 部署后是否去除 master 节点污点（允许 Pod 调度到 master）
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class K8sClusterNode(Base):
    """K8S 集群节点"""
    __tablename__ = "k8s_cluster_nodes"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("k8s_cluster_plans.id"), nullable=False)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    host_role = Column(String(16), default="worker")
    ip = Column(String(64), default="")
    hostname = Column(String(64), default="")
    username = Column(String(64), default="")
    password = Column(String(128), default="")  # 敏感
    has_password = Column(Boolean, default=False)
    ssh_port = Column(Integer, default=22)
    status = Column(String(32), default="pending")
    init_roles = Column(String(255), default="")  # control-plane,etcd
    joined_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class K8sCluster(Base):
    """多集群注册表(F5) - 把多个 K8s DataSource 聚合为命名集群, 独立 telemetry 通道。"""
    __tablename__ = "k8s_clusters"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    role = Column(String(16), default="node")  # controller / node
    datasource_id = Column(Integer, nullable=True)
    data_plane_status = Column(String(16), default="active")  # active / standby / error
    telemetry_channel = Column(String(64), default="")
    namespace_scope = Column(String(128), default="")
    target_version = Column(String(32), default="")
    agent_version = Column(String(32), default="1.0.0")
    last_check_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
