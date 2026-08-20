"""域模型: ops (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""


from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text

from app.database import Base


class ChaosExperiment(Base):
    __tablename__ = "chaos_experiments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    target_type = Column(String(32), default="pod")
    target_layer = Column(String(32), default="host")
    target_selector = Column(Text, default="{}")
    fault_type = Column(String(64), nullable=False)
    fault_params = Column(Text, default="{}")
    steady_state = Column(Text, default="{}")
    status = Column(String(32), default="pending")
    result = Column(String(32), default="")
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class ChaosRun(Base):
    __tablename__ = "chaos_runs"
    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("chaos_experiments.id"), nullable=False)
    is_steady_state_passed = Column(Boolean, default=False)
    is_auto_recovered = Column(Boolean, default=False)
    alerts_triggered = Column(Integer, default=0)
    error_budget_impact = Column(Float, default=0.0)
    duration_seconds = Column(Integer, default=0)
    steady_state_before = Column(Text, default="{}")
    steady_state_after = Column(Text, default="{}")
    description = Column(Text, default="")
    started_at = Column(DateTime, default=lambda: datetime.now())


class ChaosScenario(Base):
    __tablename__ = "chaos_scenarios"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    category = Column(String(32), default="pod")
    target_layer = Column(String(32), default="host")
    fault_type = Column(String(64), nullable=False)
    fault_params = Column(Text, default="{}")
    risk_level = Column(String(16), default="low")
    recommended_slo = Column(String(128), default="")
    is_builtin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now())


class AutoRemediation(Base):
    __tablename__ = "auto_remediations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), nullable=True)
    action_type = Column(String(32), nullable=False)
    remediation_params = Column(Text, default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class RemediationLog(Base):
    __tablename__ = "remediation_logs"

    id = Column(Integer, primary_key=True, index=True)
    remediation_id = Column(Integer, nullable=True)
    remediation_type = Column(String(16), default="rule")  # "rule" or "workflow"
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    action_type = Column(String(32), nullable=False)
    target = Column(String(128), default="")
    is_success = Column(Boolean, default=False)
    output = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


class RemediationEffect(Base):
    __tablename__ = "remediation_effects"

    id = Column(Integer, primary_key=True, index=True)
    remediation_id = Column(Integer, nullable=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    executed_at = Column(DateTime, nullable=False)
    check_at = Column(DateTime, nullable=False)
    alert_status_at_execute = Column(String(32), default="triggered")
    alert_status_at_check = Column(String(32), default="unknown")
    is_asset_recovered = Column(Boolean, default=False)
    is_alert_resolved = Column(Boolean, default=False)
    recovery_time_seconds = Column(Integer, default=0)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


class RemediationWorkflow(Base):
    __tablename__ = "remediation_workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), nullable=True)
    steps = Column(Text, default="[]")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, default="")
    ci_type = Column(String(64), default="")
    asset_id = Column(Integer, nullable=True)
    change_type = Column(String(32), default="normal")
    priority = Column(String(32), default="medium")
    status = Column(String(32), default="draft")
    risk_level = Column(String(32), default="low")
    planned_started_at = Column(DateTime, nullable=True)
    planned_ended_at = Column(DateTime, nullable=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    review_comment = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class ChangeTask(Base):
    __tablename__ = "change_tasks"

    id = Column(Integer, primary_key=True, index=True)
    change_id = Column(Integer, ForeignKey("change_requests.id"), nullable=False)
    step_order = Column(Integer, default=0)
    description = Column(String(512), default="")
    command = Column(String(1024), default="")
    status = Column(String(32), default="pending")
    result = Column(Text, default="")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    executed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class DiscoveryJob(Base):
    __tablename__ = "discovery_jobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128))
    job_type = Column(String(32), default="ssh")
    target = Column(String(256))
    job_config = Column(Text, default="{}")
    status = Column(String(32), default="pending")
    result_summary = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
    finished_at = Column(DateTime, nullable=True)


class InspectionTemplate(Base):
    """巡检模板 — 定义检查项集合"""
    __tablename__ = "inspection_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    target_ci_types = Column(Text, default="[]")
    check_items = Column(Text, default="[]")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class InspectionTask(Base):
    """巡检任务 — 选择模板 + 资产范围"""
    __tablename__ = "inspection_tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    template_id = Column(Integer, ForeignKey("inspection_templates.id"), nullable=False)
    scope_type = Column(String(32), default="manual")
    scope_filter = Column(Text, default="{}")
    asset_ids = Column(Text, default="[]")
    schedule_cron = Column(String(64), nullable=True)
    schedule_enabled = Column(Boolean, default=False)
    ai_analysis = Column(Boolean, default=True)
    status = Column(String(32), default="idle")
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class InspectionRecord(Base):
    """巡检记录 — 一次执行的结果"""
    __tablename__ = "inspection_records"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("inspection_tasks.id"), nullable=False)
    triggered_by_alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    status = Column(String(32), default="running")
    total_assets = Column(Integer, default=0)
    checked_assets = Column(Integer, default=0)
    normal_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    overall_score = Column(Float, default=0.0)
    ai_report = Column(Text, default="")
    ai_risk_summary = Column(Text, default="")
    ai_recommendations = Column(Text, default="[]")
    item_results = Column(Text, default="[]")
    started_at = Column(DateTime, default=lambda: datetime.now())
    finished_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, default=0.0)


class SecurityBaselineTemplate(Base):
    __tablename__ = "security_baseline_templates"

    id = Column(Integer, primary_key=True, index=True)
    ci_type = Column(String(32), nullable=False, index=True)
    check_key = Column(String(64), nullable=False)
    check_name = Column(String(128), nullable=False)
    category = Column(String(32), default="access")
    severity = Column(String(16), default="medium")
    description = Column(String(512), default="")
    check_method = Column(String(16), default="ssh")
    check_command = Column(String(512), default="")
    expect_match = Column(String(256), default="")
    remediation = Column(Text, default="")
    sort_order = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class AssetBaselineCheck(Base):
    __tablename__ = "asset_baseline_checks"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    template_id = Column(Integer, ForeignKey("security_baseline_templates.id"), nullable=False)
    status = Column(String(16), default="pending")
    actual_value = Column(String(512), default="")
    reason = Column(Text, default="")
    checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class RemediationEffectRecord(Base):
    __tablename__ = "remediation_effect_records"

    id = Column(Integer, primary_key=True, index=True)
    remediation_id = Column(Integer, ForeignKey("auto_remediations.id"), nullable=True, index=True)
    log_id = Column(Integer, ForeignKey("remediation_logs.id"), nullable=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True, index=True)
    status_before = Column(String(32), default="")
    status_after = Column(String(32), default="")
    effect = Column(String(16), default="")
    checked_at = Column(DateTime, nullable=True)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


class AnomalyBenchmark(Base):
    __tablename__ = "anomaly_benchmarks"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True, index=True)
    metric_name = Column(String(64), nullable=False)
    algorithm = Column(String(32), default="")
    window_minutes = Column(Integer, default=60)
    precision = Column(Float, default=0.0)
    recall = Column(Float, default=0.0)
    f1_score = Column(Float, default=0.0)
    threshold = Column(Float, default=0.0)
    labeled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class DiscoverySchedule(Base):
    __tablename__ = "discovery_schedules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    protocol = Column(String(16), default="ssh")
    target_range = Column(String(256), default="")
    port = Column(Integer, default=22)
    credential_id = Column(Integer, nullable=True)
    schedule_cron = Column(String(64), default="0 2 * * *")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class DiscoveryResult(Base):
    __tablename__ = "discovery_results"

    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("discovery_schedules.id"), nullable=True, index=True)
    ip = Column(String(64), nullable=False)
    hostname = Column(String(128), default="")
    port = Column(Integer, default=0)
    status = Column(String(16), default="discovered")
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True, index=True)
    os_type = Column(String(32), default="")
    services = Column(Text, default="")
    raw_output = Column(Text, default="")
    discovered_at = Column(DateTime, default=lambda: datetime.now())


class ConfigBaseline(Base):
    """配置基线 — 记录资产某配置项的内容快照用于漂移检测"""
    __tablename__ = "config_baselines"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    config_key = Column(String(128), nullable=False)          # 配置项唯一标识(如 nginx.conf / max_connections)
    config_name = Column(String(128), default="")             # 配置项显示名
    category = Column(String(32), default="middleware")       # 分类: system/nginx/mysql/redis/k8s/app/custom
    source_command = Column(Text, default="")                 # 采集该配置的 SSH 命令
    content = Column(Text, default="")                        # 基线内容快照
    content_hash = Column(String(64), default="")             # 内容哈希(快速判等)
    version = Column(Integer, default=1)                      # 基线版本(每次更新+1)
    baseline_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, nullable=True)


class ConfigDriftRecord(Base):
    """配置漂移记录 — 一次检测发现基线与实际配置不一致的结果"""
    __tablename__ = "config_drift_records"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    baseline_id = Column(Integer, ForeignKey("config_baselines.id"), nullable=True)
    config_key = Column(String(128), nullable=False)
    config_name = Column(String(128), default="")
    category = Column(String(32), default="middleware")
    baseline_content = Column(Text, default="")               # 基线内容
    current_content = Column(Text, default="")                # 当前采集内容
    drift_type = Column(String(16), default="content")        # content/added/removed
    diff_text = Column(Text, default="")                      # 差异展示文本
    drift_count = Column(Integer, default=0)                  # 差异行数
    severity = Column(String(16), default="medium")           # low/medium/high/critical
    status = Column(String(16), default="open")               # open/acknowledged/resolved/ignored
    ai_assessment = Column(Text, default="")                  # AI 评估(JSON: 根因/影响/推荐修正/风险)
    resolved_at = Column(DateTime, nullable=True)
    detected_at = Column(DateTime, default=lambda: datetime.now())
    created_at = Column(DateTime, default=lambda: datetime.now())


class ComponentCatalog(Base):
    """组件应用商店目录 — 官方中间件/组件清单(对标 Bitnami catalog / Terraform Registry)"""
    __tablename__ = "component_catalog"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False, unique=True)     # 组件名(如 redis/mysql/kafka)
    display_name = Column(String(128), default="")             # 显示名(如 Redis)
    category = Column(String(32), default="middleware")        # database/middleware/cache/message/web/observability
    version = Column(String(32), default="")                   # 默认版本(tag/chart version)
    description = Column(String(512), default="")
    icon = Column(String(16), default="🐳")
    docker_image = Column(String(128), default="")             # docker 镜像
    helm_chart = Column(String(128), default="")               # helm chart(如 bitnami/redis)
    helm_repo = Column(String(256), default="")                # helm 仓库
    source = Column(String(256), default="")                   # native 安装来源(如 清华镜像/官方源) — 定死只读展示
    default_port = Column(Integer, default=0)
    deploy_types = Column(Text, default="[]")                  # 支持的部署方式 ["native","docker","helm","ha"]
    native_script = Column(Text, default="")                   # 传统部署脚本(yum/apt/命令)
    compose_yaml = Column(Text, default="")                    # docker compose 内容
    ha_config = Column(Text, default="{}")                     # 高可用配置(JSON: 副本/集群开关)
    config_keys = Column(Text, default="")                     # 关联 config_drift 配置项键(逗号分隔)
    param_schema = Column(Text, default="[]")                  # 组件级定制参数模板(JSON 数组, 见 CONTRACT.md)
    complexity = Column(String(16), default="simple")          # simple/medium/complex
    enabled = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class ComponentInstall(Base):
    """组件安装/部署记录 — 记录某资产上安装的组件实例及其状态与检查结果"""
    __tablename__ = "component_installs"

    id = Column(Integer, primary_key=True, index=True)
    component_id = Column(Integer, ForeignKey("component_catalog.id"), nullable=False, index=True)
    component_name = Column(String(64), default="")            # 冗余组件名
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    deploy_type = Column(String(16), default="docker")         # native/docker/helm/ha
    name_space = Column(String(64), default="")                # helm 部署命名空间
    release_name = Column(String(128), default="")             # helm release 名
    deploy_path = Column(String(256), default="")              # compose/脚本部署路径
    port = Column(Integer, default=0)                          # 实例端口
    status = Column(String(16), default="deploying")           # deploying/running/failed/stopped
    config_check_status = Column(String(16), default="pending")# pending/pass/drift/config error
    health_status = Column(String(16), default="unknown")      # healthy/degraded/unhealthy
    config_result = Column(Text, default="")                   # 配置优化检查结果(JSON)
    health_result = Column(Text, default="")                   # 高可用/巡检结果(JSON)
    vuln_result = Column(Text, default="")                     # 漏洞检查结果(JSON)
    ai_analysis = Column(Text, default="")                     # AI 健康分析(JSON)
    deploy_log = Column(Text, default="")                      # 部署日志(截断)
    deploy_plan_id = Column(Integer, nullable=True)            # 关联 deploy.plans
    deploy_params = Column(Text, default="{}")                 # 本次部署定制参数快照(JSON {key:value})
    report_json = Column(Text, default="")                     # AI 可直接交付部署报告(JSON) — 落库持久化
    events_json = Column(Text, default="")                     # 部署完整结构化事件(JSON数组, 供历史回放/续 AI 对话)
    pending_decision_json = Column(Text, default="null")       # 待用户决策卡片(JSON) / "null"=无, 按安装记录独立
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
