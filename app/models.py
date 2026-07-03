import json
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text

from app.database import Base


class ChaosExperiment(Base):
    __tablename__ = "chaos_experiments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    target_type = Column(String(32), default="pod")
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
    steady_state_passed = Column(Boolean, default=False)
    alerts_triggered = Column(Integer, default=0)
    error_budget_impact = Column(Float, default=0.0)
    duration_seconds = Column(Integer, default=0)
    steady_state_before = Column(Text, default="{}")
    steady_state_after = Column(Text, default="{}")
    notes = Column(Text, default="")
    started_at = Column(DateTime, default=lambda: datetime.now())


class ChaosScenario(Base):
    __tablename__ = "chaos_scenarios"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    category = Column(String(32), default="pod")
    fault_type = Column(String(64), nullable=False)
    fault_params = Column(Text, default="{}")
    risk_level = Column(String(16), default="low")
    recommended_slo = Column(String(128), default="")
    is_builtin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now())


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(32), default="admin")
    created_at = Column(DateTime, default=lambda: datetime.now())


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    type = Column(String(64), nullable=False)
    ci_type = Column(String(32), default="server")
    parent_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    ip = Column(String(64), default="")
    status = Column(String(32), default="offline")
    tags = Column(String(256), default="")
    ci_attributes = Column(Text, default="{}")
    k8s_cluster = Column(String(128), default="")
    connection_type = Column(String(32), default="ssh")
    connection_config = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now())
    last_checked = Column(DateTime, nullable=True)
    latency_ms = Column(Integer, nullable=True)


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    metric_name = Column(String(64), nullable=False)
    condition = Column(String(8), nullable=False)
    threshold = Column(Float, nullable=False)
    severity = Column(String(32), default="warning")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class AlertSilence(Base):
    __tablename__ = "alert_silences"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), nullable=False)
    until = Column(DateTime, nullable=False)
    reason = Column(String(256), default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), nullable=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    metric_name = Column(String(64), nullable=False)
    actual_value = Column(Float, nullable=False)
    threshold = Column(Float, nullable=False)
    severity = Column(String(32), nullable=False)
    status = Column(String(32), default="triggered")
    message = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
    resolved_at = Column(DateTime, nullable=True)


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)
    type = Column(String(32), nullable=False)
    config = Column(Text, default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    channel_id = Column(Integer, ForeignKey("notification_channels.id"), nullable=True)
    channel_type = Column(String(32), nullable=False)
    recipient = Column(String(256), default="")
    title = Column(String(256), default="")
    content = Column(Text, default="")
    success = Column(Boolean, default=False)
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    severity = Column(String(32), default="warning")
    status = Column(String(32), default="open")
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    alert_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())
    resolved_at = Column(DateTime, nullable=True)


class IncidentAlert(Base):
    __tablename__ = "incident_alerts"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    symptom = Column(Text, default="")
    root_cause = Column(Text, default="")
    solution = Column(Text, default="")
    tags = Column(String(256), default="")
    severity = Column(String(32), default="warning")
    asset_type = Column(String(32), default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class AlertKbLink(Base):
    __tablename__ = "alert_kb_links"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    kb_id = Column(Integer, ForeignKey("knowledge_base.id"), nullable=False)


class AutoRemediation(Base):
    __tablename__ = "auto_remediations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), nullable=True)
    action_type = Column(String(32), nullable=False)
    params = Column(Text, default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class RemediationLog(Base):
    __tablename__ = "remediation_logs"

    id = Column(Integer, primary_key=True, index=True)
    remediation_id = Column(Integer, ForeignKey("auto_remediations.id"), nullable=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    action_type = Column(String(32), nullable=False)
    target = Column(String(128), default="")
    success = Column(Boolean, default=False)
    output = Column(Text, default="")
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
    last_scrape = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    permissions = Column(String(256), default="read")
    last_used = Column(DateTime, nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    value = Column(Text, default="")
    description = Column(String(256), default="")
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    type = Column(String(32), nullable=False)
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    summary = Column(Text, default="")
    data = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


class AlertSuppression(Base):
    __tablename__ = "alert_suppressions"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), nullable=True)
    rule_name = Column(String(128), default="")
    metric_name = Column(String(64), default="")
    asset_id = Column(Integer, nullable=True)
    suppressed_count = Column(Integer, default=1)
    reason = Column(String(64), default="dedup")
    created_at = Column(DateTime, default=lambda: datetime.now())


class AnomalyConfig(Base):
    __tablename__ = "anomaly_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    metric_name = Column(String(64), nullable=False)
    asset_id = Column(Integer, nullable=True)
    algorithm = Column(String(32), default="sigma")
    sensitivity = Column(Float, default=3.0)
    window_size = Column(Integer, default=20)
    period = Column(Integer, default=12)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class AlertEscalation(Base):
    __tablename__ = "alert_escalations"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    from_severity = Column(String(32), nullable=False)
    to_severity = Column(String(32), nullable=False)
    reason = Column(String(256), default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


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
    first_seen = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    count = Column(Integer, default=1)
    severity = Column(String(32), default="info")
    created_at = Column(DateTime, default=lambda: datetime.now())


class Runbook(Base):
    __tablename__ = "runbooks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    category = Column(String(64), default="general")
    symptom = Column(Text, default="")
    diagnosis = Column(Text, default="")
    steps = Column(Text, default="")
    tags = Column(String(256), default="")
    severity = Column(String(32), default="warning")
    asset_type = Column(String(32), default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    channel_type = Column(String(32), default="")
    title_template = Column(Text, default="")
    body_template = Column(Text, default="")
    severity = Column(String(32), default="warning")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class RemediationWorkflow(Base):
    __tablename__ = "remediation_workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), nullable=True)
    steps = Column(Text, default="[]")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class AlertSilenceSchedule(Base):
    __tablename__ = "alert_silence_schedules"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), nullable=True)
    metric_name = Column(String(64), default="")
    asset_id = Column(Integer, nullable=True)
    cron_expr = Column(String(64), default="0 2 * * 0")
    duration_minutes = Column(Integer, default=120)
    reason = Column(String(256), default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class LogAnomalyRule(Base):
    __tablename__ = "log_anomaly_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    source = Column(String(32), default="k8s")
    keyword = Column(String(256), default="")
    regex_pattern = Column(String(512), default="")
    threshold = Column(Integer, default=10)
    window_minutes = Column(Integer, default=5)
    severity = Column(String(32), default="warning")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


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


class DashboardCardConfig(Base):
    __tablename__ = "dashboard_card_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    card_type = Column(String(64), nullable=False)
    title = Column(String(128), default="")
    config = Column(Text, default="{}")
    position = Column(Integer, default=0)
    visible = Column(Boolean, default=True)


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


class PredictionModel(Base):
    __tablename__ = "prediction_models"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    metric_name = Column(String(64), nullable=False)
    asset_id = Column(Integer, nullable=True)
    model_type = Column(String(32), default="linear")
    params = Column(Text, default="{}")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class AlertWebhook(Base):
    __tablename__ = "alert_webhooks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    url = Column(String(512), nullable=False)
    secret = Column(String(128), default="")
    retry_count = Column(Integer, default=3)
    timeout = Column(Integer, default=10)
    enabled = Column(Boolean, default=True)
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
    planned_start = Column(DateTime, nullable=True)
    planned_end = Column(DateTime, nullable=True)
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
    executed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    executed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


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
    required = Column(Boolean, default=False)
    default_value = Column(String(256), default="")
    options = Column(Text, default="")
    order = Column(Integer, default=0)
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
    last_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class AlertEventLink(Base):
    __tablename__ = "alert_event_links"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("k8s_events.id"), nullable=False)
    relation = Column(String(32), default="triggered_by")
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
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    comment = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


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
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    duration_ms = Column(Float, default=0)
    status = Column(String(32), default="OK")
    tags = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now())


class DiscoveryJob(Base):
    __tablename__ = "discovery_jobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128))
    job_type = Column(String(32), default="ssh")
    target = Column(String(256))
    config = Column(Text, default="{}")
    status = Column(String(32), default="pending")
    result_summary = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
    finished_at = Column(DateTime, nullable=True)


class ExtCmdbConfig(Base):
    __tablename__ = "ext_cmdb_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128))
    cmdb_type = Column(String(32), default="generic")
    api_url = Column(String(512))
    auth_config = Column(Text, default="{}")
    sync_interval = Column(Integer, default=60)
    last_sync = Column(DateTime, nullable=True)
    enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now())


class TraceAnomalyConfig(Base):
    __tablename__ = "trace_anomaly_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128))
    service_name = Column(String(128), default="")
    latency_threshold_ms = Column(Float, default=1000)
    error_rate_threshold = Column(Float, default=0.05)
    enabled = Column(Boolean, default=True)
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
    last_sync = Column(DateTime, nullable=True)
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
    start_time = Column(DateTime)
    end_time = Column(DateTime)
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


class BlueGreenDeploy(Base):
    __tablename__ = "blue_green_deploys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128))
    namespace = Column(String(64), default="default")
    active_label = Column(String(64), default="blue")
    standby_label = Column(String(64), default="green")
    active_replicas = Column(Integer, default=3)
    standby_replicas = Column(Integer, default=3)
    status = Column(String(32), default="active")
    created_at = Column(DateTime, default=lambda: datetime.now())


class ClusterAnomalyEvent(Base):
    __tablename__ = "cluster_anomaly_events"

    id = Column(Integer, primary_key=True, index=True)
    anomaly_type = Column(String(64))
    cluster = Column(String(128), default="default")
    message = Column(Text, default="")
    severity = Column(String(32), default="warning")
    count = Column(Integer, default=1)
    first_seen = Column(DateTime)
    last_seen = Column(DateTime)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now())


# ============================================================
# AI Agent 模块 — 参考 SxDevOps AIOps Agent 架构
# ============================================================

class AIProvider(Base):
    """LLM 模型提供商配置"""
    __tablename__ = "ai_providers"

    PROVIDER_OPENAI = "openai_compatible"
    PROVIDER_CHOICES = [PROVIDER_OPENAI]

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    provider_type = Column(String(32), default=PROVIDER_OPENAI)
    base_url = Column(String(255), default="")
    api_key_encrypted = Column(Text, default="")
    default_model = Column(String(128), default="")
    temperature = Column(Float, default=0.2)
    max_tokens = Column(Integer, default=10000)
    timeout_seconds = Column(Integer, default=30)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def set_api_key(self, value):
        from cryptography.fernet import Fernet
        import hashlib, base64
        value = (value or "").strip()
        if not value:
            self.api_key_encrypted = ""
            return
        seed = b"aiops-agent-provider-key-seed"
        key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
        self.api_key_encrypted = Fernet(key).encrypt(value.encode("utf-8")).decode("utf-8")

    def get_api_key(self):
        if not self.api_key_encrypted:
            return ""
        try:
            from cryptography.fernet import Fernet
            import hashlib, base64
            seed = b"aiops-agent-provider-key-seed"
            key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
            return Fernet(key).decrypt(self.api_key_encrypted.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""


class AgentConfig(Base):
    """Agent 配置"""
    __tablename__ = "agent_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, default="default")
    default_provider_id = Column(Integer, ForeignKey("ai_providers.id"), nullable=True)
    system_prompt = Column(Text, default="")
    welcome_message = Column(String(255), default="你好，我可以帮你查询资源、分析告警、生成运维任务等。")
    suggested_questions = Column(Text, default="[]")
    is_enabled = Column(Boolean, default=True)
    allow_action_execution = Column(Boolean, default=True)
    require_confirmation = Column(Boolean, default=True)
    max_history_messages = Column(Integer, default=12)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def get_suggested_questions(self):
        try:
            return json.loads(self.suggested_questions) if self.suggested_questions else []
        except (json.JSONDecodeError, TypeError):
            return []


class ChatSession(Base):
    """AI 会话"""
    __tablename__ = "chat_sessions"

    STATUS_ACTIVE = "active"
    STATUS_ARCHIVED = "archived"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(128), default="新会话")
    status = Column(String(16), default=STATUS_ACTIVE)
    context = Column(Text, default="{}")
    last_message_at = Column(DateTime, default=lambda: datetime.now())
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class ChatMessage(Base):
    """会话消息"""
    __tablename__ = "chat_messages"

    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_SYSTEM = "system"

    TYPE_TEXT = "text"
    TYPE_ANALYSIS = "analysis"
    TYPE_ACTION = "action"
    TYPE_ERROR = "error"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String(16), nullable=False)
    message_type = Column(String(16), default=TYPE_TEXT)
    content = Column(Text, default="")
    citations = Column(Text, default="[]")
    tool_calls = Column(Text, default="[]")
    msg_metadata = Column("metadata", Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now())


class MCPServer(Base):
    """MCP 服务注册"""
    __tablename__ = "mcp_servers"

    TYPE_HTTP = "http"
    TYPE_PLATFORM_BUILTIN = "platform_builtin"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    server_type = Column(String(16), default=TYPE_PLATFORM_BUILTIN)
    endpoint = Column(String(255), default="")
    description = Column(String(255), default="")
    auth_config = Column(Text, default="{}")
    tool_whitelist = Column(Text, default="[]")
    is_builtin = Column(Boolean, default=False)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class PendingAction(Base):
    """待确认动作"""
    __tablename__ = "pending_actions"

    RISK_LOW = "low"
    RISK_MEDIUM = "medium"
    RISK_HIGH = "high"
    RISK_CRITICAL = "critical"

    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_EXECUTING = "executing"
    STATUS_CANCELED = "canceled"
    STATUS_EXECUTED = "executed"
    STATUS_FAILED = "failed"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True)
    action_type = Column(String(64), nullable=False)
    title = Column(String(128), default="")
    risk_level = Column(String(16), default=RISK_LOW)
    reason = Column(String(500), nullable=True)
    status = Column(String(16), default=STATUS_PENDING)
    action_payload = Column(Text, default="{}")
    result_payload = Column(Text, default="{}")
    confirmed_by = Column(String(64), default="")
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class ToolInvocation(Base):
    """工具调用记录"""
    __tablename__ = "tool_invocations"

    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True)
    tool_name = Column(String(64), nullable=False)
    status = Column(String(16), default=STATUS_PENDING)
    latency_ms = Column(Integer, default=0)
    request_payload = Column(Text, default="{}")
    response_summary = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now())


class SystemPostureRecord(Base):
    """系统态势 SLA 每日快照"""
    __tablename__ = "system_posture_records"

    id = Column(Integer, primary_key=True, index=True)
    day = Column(String(16), nullable=False, index=True)
    system_key = Column(String(64), nullable=False)
    system_name = Column(String(128), default="")
    environment = Column(String(32), default="prod")
    domain = Column(String(64), default="")
    status = Column(String(16), default="unknown")
    sla_value = Column(Float, nullable=True)
    health_score = Column(Integer, nullable=True)
    alerts_count = Column(Integer, default=0)
    incidents_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())


# ==================== SRE 相关模型 ====================

class SLOConfig(Base):
    __tablename__ = "slo_configs"
    """SLO 配置"""
    id = Column(Integer, primary_key=True)
    service_name = Column(String(100), nullable=False)  # 服务名
    slo_target = Column(Float, nullable=False)       # 目标可用性 0.999
    window_days = Column(Integer, default=30)       # 窗口天数
    total_requests = Column(Integer, default=0)      # 总请求数
    error_requests = Column(Integer, default=0)     # 错误请求数
    status = Column(String(20), default='healthy')   # healthy/warning/critical
    created_by = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ErrorBudget(Base):
    __tablename__ = "error_budgets"
    """错误预算记录"""
    id = Column(Integer, primary_key=True)
    slo_id = Column(Integer, ForeignKey('slo_configs.id'))  # 关联的 SLO
    service_name = Column(String(100), nullable=False)
    period_start = Column(DateTime)                     # 周期开始
    period_end = Column(DateTime)                     # 周期结束
    budget_total = Column(Float, default=100)       # 总预算 %
    budget_consumed = Column(Float, default=0)      # 已消耗 %
    budget_remaining = Column(Float, default=100)     # 剩余 %
    burn_rate = Column(Float, default=0)              # 消耗速率
    status = Column(String(20), default='healthy')
    created_at = Column(DateTime, default=datetime.utcnow)


class OnCallSchedule(Base):
    __tablename__ = "oncall_schedules"
    """值班表"""
    id = Column(Integer, primary_key=True)
    team_name = Column(String(50), nullable=False)  # 团队名
    rotation_type = Column(String(20), default='weekly')  # weekly/monthly
    members = Column(Text)                          # 成员列表 JSON
    schedule = Column(Text)                         # 轮值表 JSON
    current_oncall = Column(String(50))             # 当前值班人
    current_period_start = Column(DateTime)         # 当前周期开始
    current_period_end = Column(DateTime)          # 当前周期结束
    created_by = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EscalationPolicy(Base):
    __tablename__ = "escalation_policies"
    """升级策略"""
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)       # 策略名
    levels = Column(Text)                           # 升级级别 JSON
    wait_minutes = Column(Text)                      # 每级等待时间 JSON
    notify_channels = Column(Text)                  # 通知渠道 JSON
    is_active = Column(Boolean, default=True)
    created_by = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SLARecord(Base):
    __tablename__ = "sla_records"
    """SLA 协议记录"""
    id = Column(Integer, primary_key=True)
    service_name = Column(String(100), nullable=False)
    sla_target = Column(Float, nullable=False)        # SLA 目标 0.999
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    uptime_seconds = Column(Integer, default=0)
    downtime_seconds = Column(Integer, default=0)
    achieved_sla = Column(Float, default=0.0)         # 实际达成的 SLA
    penalty = Column(String(50), default="none")       # 处罚: none/warning/penalty
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)


class AvailabilityReport(Base):
    __tablename__ = "availability_reports"
    """可用性报告"""
    id = Column(Integer, primary_key=True)
    service_name = Column(String(100), nullable=False)
    report_date = Column(DateTime)                     # 报告日期
    total_uptime = Column(Integer, default=0)          # 总运行时间(秒)
    total_downtime = Column(Integer, default=0)        # 总停机时间(秒)
    availability_pct = Column(Float, default=100.0)    # 可用性百分比
    incident_count = Column(Integer, default=0)         # 故障次数
    total_duration = Column(Integer, default=0)         # 总时长(秒)
    created_at = Column(DateTime, default=datetime.utcnow)
