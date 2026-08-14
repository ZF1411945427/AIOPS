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
