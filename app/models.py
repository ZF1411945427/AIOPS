import json
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint

from app.database import Base


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, nullable=False, index=True)
    description = Column(String(256), default="")
    is_system = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())


class RoleMenu(Base):
    __tablename__ = "role_menus"
    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    menu_key = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now())


class RolePermission(Base):
    """资源级 RBAC 策略（对齐 Ongrid Casbin resource:action 策略矩阵）。

    resource=alert/asset/incident/deploy/k8s/user/role/config/report/...;
    action=read/write/execute/delete。superuser 角色自动拥有全部权限（绕过策略）。
    """
    __tablename__ = "role_permissions"
    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    resource = Column(String(64), nullable=False, index=True)
    action = Column(String(32), nullable=False)  # read / write / execute / delete
    created_at = Column(DateTime, default=lambda: datetime.now())
    __table_args__ = (UniqueConstraint("role_id", "resource", "action", name="uq_role_permission"),)


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


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(32), default="admin")
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now())


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


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    # G1: kind 告警规则类型化 metric_raw / anomaly / forecast / burn_rate
    kind = Column(String(24), default="metric_raw", nullable=False)
    metric_name = Column(String(64), nullable=False)
    condition = Column(String(8), nullable=False)
    threshold = Column(Float, nullable=False)
    # G1: 各 kind 专用参数(JSON)
    config_json = Column(Text, default="{}")
    severity = Column(String(32), default="warning")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class AlertSilence(Base):
    __tablename__ = "alert_silences"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), nullable=True)
    expires_at = Column(DateTime, nullable=False)
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
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)
    type = Column(String(32), nullable=False)
    channel_config = Column(Text, default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    # P1-2: IM 双向通道字段
    bidirectional = Column(Boolean, default=False)        # 是否双向（支持指令回传）
    callback_token = Column(String(128), default="")      # IM 平台回调校验 token / Verify Token / Signing Key
    callback_secret = Column(String(128), default="")     # 飞书 Encrypt Key / 钉钉 Secret / 企微 Token
    default_sub_agent = Column(String(64), default="auto")  # 该通道默认使用的子专家


class ImIncomingMessage(Base):
    """IM 双向通道收到的指令消息（ChatOps 闭环）。"""
    __tablename__ = "im_incoming_messages"

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_REPLIED = "replied"
    STATUS_FAILED = "failed"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("notification_channels.id"), nullable=True)
    platform = Column(String(32), nullable=False)         # feishu / dingtalk / wecom
    sender_id = Column(String(128), default="")           # 发送者 ID（open_id / userid / userid）
    sender_name = Column(String(128), default="")         # 发送者名称
    chat_id = Column(String(128), default="")             # 群/会话 ID
    raw_payload = Column(Text, default="")                # 原始回调 payload
    command = Column(String(64), default="")              # 指令名：ai / alert / help
    message_text = Column(Text, default="")               # 消息文本
    status = Column(String(32), default=STATUS_PENDING)
    reply_text = Column(Text, default="")                 # Agent 回复内容
    session_id = Column(Integer, nullable=True)           # 关联的 ChatSession.id
    created_at = Column(DateTime, default=lambda: datetime.now())
    processed_at = Column(DateTime, nullable=True)


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    channel_id = Column(Integer, ForeignKey("notification_channels.id"), nullable=True)
    channel_type = Column(String(32), nullable=False)
    recipient = Column(String(256), default="")
    title = Column(String(256), default="")
    notification_content = Column(Text, default="")
    is_success = Column(Boolean, default=False)
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
    impact = Column(String(32), default="high")
    description = Column(Text, default="")
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    review_comment = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
    resolved_at = Column(DateTime, nullable=True)
    ai_rca_result = Column(Text, default="")
    ai_rca_at = Column(DateTime, nullable=True)


class IncidentAlert(Base):
    __tablename__ = "incident_alerts"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)


class IncidentApproval(Base):
    __tablename__ = "incident_approvals"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(32), nullable=False)  # submit / approve / reject
    description = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


class InvestigationReport(Base):
    """C2: 自动调查结构化报告（告警/故障触发后由 auto_investigator 生成）。

    investigation_type: root_cause / performance / security / capacity ...
    三态 status: running / completed / failed
    """
    __tablename__ = "investigation_reports"

    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    investigation_type = Column(String(32), default="root_cause")
    title = Column(String(256), default="")
    status = Column(String(16), default=STATUS_RUNNING)
    # 结构化报告内容（JSON）：root_cause / evidence / recommendation / risk / summary
    report_data = Column(Text, default="{}")
    report_md = Column(Text, default="")
    evidence_summary = Column(Text, default="")
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
    completed_at = Column(DateTime, nullable=True)



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
    source_type = Column(String(32), default="manual")
    sop_steps = Column(Text, default="[]")
    version_number = Column(Integer, default=1)
    change_log = Column(Text, default="")
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


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    permissions = Column(String(256), default="read")
    last_used_at = Column(DateTime, nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    config_value = Column(Text, default="")
    description = Column(String(256), default="")
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    type = Column(String(32), nullable=False)
    period_started_at = Column(DateTime, nullable=True)
    period_ended_at = Column(DateTime, nullable=True)
    summary = Column(Text, default="")
    report_data = Column(Text, default="")
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
    first_seen_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
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
    log_level = Column(String(32), default="")
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
    model_params = Column(Text, default="{}")
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


class ReportSchedule(Base):
    __tablename__ = "report_schedules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    report_type = Column(String(32), default="daily")
    cron_expr = Column(String(128), default="0 8 * * *")
    channel = Column(String(32), default="email")
    channel_config = Column(Text, default="{}")
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class AlertEventLink(Base):
    __tablename__ = "alert_event_links"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("k8s_events.id"), nullable=False)
    relation = Column(String(32), default="triggered_by")
    created_at = Column(DateTime, default=lambda: datetime.now())


class AlertSessionLink(Base):
    """告警与 AI 会话的关联"""
    __tablename__ = "alert_session_links"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    context_summary = Column(Text, default="")
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


class TraceAnomalyConfig(Base):
    __tablename__ = "trace_anomaly_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128))
    service_name = Column(String(128), default="")
    latency_threshold_ms = Column(Float, default=1000)
    error_rate_threshold = Column(Float, default=0.05)
    check_window_minutes = Column(Integer, default=30)
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


class ClusterAnomalyEvent(Base):
    __tablename__ = "cluster_anomaly_events"

    id = Column(Integer, primary_key=True, index=True)
    anomaly_type = Column(String(64))
    cluster = Column(String(128), default="default")
    message = Column(Text, default="")
    severity = Column(String(32), default="warning")
    count = Column(Integer, default=1)
    first_seen_at = Column(DateTime)
    last_seen_at = Column(DateTime)
    is_resolved = Column(Boolean, default=False)
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
        from app.config import PROVIDER_ENCRYPT_SEED
        value = (value or "").strip()
        if not value:
            self.api_key_encrypted = ""
            return
        seed = PROVIDER_ENCRYPT_SEED.encode("utf-8")
        key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
        self.api_key_encrypted = Fernet(key).encrypt(value.encode("utf-8")).decode("utf-8")

    def get_api_key(self):
        if not self.api_key_encrypted:
            return ""
        try:
            from cryptography.fernet import Fernet
            import hashlib, base64
            from app.config import PROVIDER_ENCRYPT_SEED
            seed = PROVIDER_ENCRYPT_SEED.encode("utf-8")
            key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
            return Fernet(key).decrypt(self.api_key_encrypted.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""


class SecretVault(Base):
    """集中凭据保险库：加密存储连接密码/Token/API Key，连接配置只存 {{secret:name}} 引用"""
    __tablename__ = "secret_vaults"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(String(256), default="")
    value_type = Column(String(32), default="password")
    scope = Column(String(64), default="global")
    secret_value_encrypted = Column(Text, default="")
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


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


class SubAgent(Base):
    """子智能体（Sub-agent）定义 — 按域分派的专家 Agent。

    Coordinator Agent 根据用户消息关键词路由到对应子专家，
    子专家使用专属 system_prompt + 工具白名单，实现 Multi-Agent Orchestration。
    domain 取值: sre / network / database / middleware / k8s / general
    """
    __tablename__ = "sub_agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, nullable=False)          # 如 "sre_expert"
    display_name = Column(String(128), default="")                   # 如 "SRE 可靠性专家"
    domain = Column(String(32), nullable=False)                      # sre/network/database/middleware/k8s/general
    description = Column(Text, default="")
    system_prompt = Column(Text, default="")
    tool_whitelist = Column(Text, default="[]")                      # JSON 数组，工具名白名单；空数组=继承全部工具
    keywords = Column(Text, default="[]")                            # JSON 数组，路由关键词
    icon = Column(String(16), default="🤖")                          # 前端展示图标
    color = Column(String(16), default="#6366f1")                    # 前端展示颜色
    is_enabled = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def get_tool_whitelist(self):
        try:
            return json.loads(self.tool_whitelist) if self.tool_whitelist else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_keywords(self):
        try:
            return json.loads(self.keywords) if self.keywords else []
        except (json.JSONDecodeError, TypeError):
            return []


class ChatSession(Base):
    """AI 会话"""
    __tablename__ = "chat_sessions"

    STATUS_ACTIVE = "active"
    STATUS_ARCHIVED = "archived"

    MODE_AGENT = "agent"
    MODE_CHAT = "chat"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(128), default="新会话")
    status = Column(String(16), default=STATUS_ACTIVE)
    context = Column(Text, default="{}")
    last_message_at = Column(DateTime, default=lambda: datetime.now())
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
    provider_id = Column(Integer, nullable=True)
    mode = Column(String(16), default=MODE_AGENT)
    linked_asset_ids = Column(Text, default="[]")
    sub_agent = Column(String(64), default="auto")  # auto/sre/network/database/middleware/k8s/general


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
    message_content = Column(Text, default="")
    citations = Column(Text, default="[]")
    tool_calls = Column(Text, default="[]")
    metadata_json = Column("metadata", Text, default="{}")
    sub_agent = Column(String(64), default="")  # 该消息归属的子智能体（空=会话默认）
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
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True)
    run_id = Column(Integer, nullable=True)
    node_run_id = Column(Integer, nullable=True)
    action_type = Column(String(64), nullable=False)
    title = Column(String(128), default="")
    risk_level = Column(String(16), default=RISK_LOW)
    reason = Column(String(500), nullable=True)
    status = Column(String(16), default=STATUS_PENDING)
    action_payload = Column(Text, default="{}")
    result_payload = Column(Text, default="{}")
    review_result = Column(Text, default="")  # A4: LLM reviewer 二签结果 JSON
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


class BackgroundJob(Base):
    """后台异步任务状态追踪（支持长耗时任务如安装、部署）"""
    __tablename__ = "background_jobs"

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CANCELED = "canceled"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(64), unique=True, nullable=False, index=True)  # UUID，供外部轮询
    action_type = Column(String(64), nullable=False)  # install_package / run_command / restart_service 等
    title = Column(String(128), default="")
    status = Column(String(16), default=STATUS_PENDING)  # pending / running / success / failed / canceled
    progress = Column(Integer, default=0)  # 0-100
    progress_message = Column(String(256), default="")  # 当前步骤描述
    result_payload = Column(Text, default="{}")  # JSON 最终结果
    error_message = Column(String(512), default="")
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True)
    pending_action_id = Column(Integer, ForeignKey("pending_actions.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


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
    period_started_at = Column(DateTime)                     # 周期开始
    period_ended_at = Column(DateTime)                     # 周期结束
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
    current_period_started_at = Column(DateTime)         # 当前周期开始
    current_period_ended_at = Column(DateTime)          # 当前周期结束
    is_auto_rotate = Column(Boolean, default=True)     # 是否自动轮转
    holidays = Column(Text, default="[]")           # 节假日 JSON 列表
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
    period_started_at = Column(DateTime)
    period_ended_at = Column(DateTime)
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
    reported_at = Column(DateTime)                     # 报告日期
    total_uptime = Column(Integer, default=0)          # 总运行时间(秒)
    total_downtime = Column(Integer, default=0)        # 总停机时间(秒)
    availability_pct = Column(Float, default=100.0)    # 可用性百分比
    incident_count = Column(Integer, default=0)         # 故障次数
    total_duration = Column(Integer, default=0)         # 总时长(秒)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── 知识库 RAG：文档管理 + 向量切片 ───
class KbDocument(Base):
    """知识库文档（支持上传 md/txt/pdf/docx，可关联 KnowledgeBase 条目或独立存在）"""
    __tablename__ = "kb_documents"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_base.id"), nullable=True)
    title = Column(String(256), nullable=False)
    source_type = Column(String(32), default="manual")   # manual / upload / alert_case / incident_case
    file_path = Column(String(512), default="")          # 上传文件原始存储路径
    file_ext = Column(String(16), default="")            # 文件扩展名 md/txt/pdf/docx
    content = Column(Text, default="")                   # 全文内容
    chunk_count = Column(Integer, default=0)             # 切片数量
    status = Column(String(32), default="pending")       # pending / indexed / failed
    tags = Column(String(256), default="")
    asset_type = Column(String(32), default="")
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)  # 关联具体资产（部署报告用）
    severity = Column(String(32), default="warning")
    index_engine = Column(String(16), default="v1")        # v1 / v2 / both（标识索引归属引擎）
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class KbChunk(Base):
    """文档切片 + 向量索引（embedding 存 JSON 字符串，兼容 SQLite；升级 pgvector 后改 vector 类型）"""
    __tablename__ = "kb_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("kb_documents.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)        # 切片序号
    content = Column(Text, nullable=False)               # 切片文本
    embedding = Column(Text, default="")                 # 向量 JSON 字符串
    embedding_mode = Column(String(32), default="tfidf") # tfidf / provider
    token_count = Column(Integer, default=0)
    tags = Column(String(256), default="")
    asset_type = Column(String(32), default="")
    severity = Column(String(32), default="warning")
    created_at = Column(DateTime, default=lambda: datetime.now())


# ─── SOP 工作流引擎：模板 / 执行实例 / 节点执行记录 ───
class WorkflowTemplate(Base):
    """SOP 工作流模板（可复用的运维剧本，DAG 节点编排）"""
    __tablename__ = "workflow_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    category = Column(String(64), default="generic")
    trigger_type = Column(String(32), default="manual")
    trigger_condition = Column(Text, default="")
    nodes = Column(Text, default="[]")
    edges = Column(Text, default="[]")
    risk_level = Column(String(32), default="medium")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def get_nodes(self):
        try:
            return json.loads(self.nodes) if self.nodes else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_edges(self):
        try:
            return json.loads(self.edges) if self.edges else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_trigger_condition(self):
        try:
            return json.loads(self.trigger_condition) if self.trigger_condition else {}
        except (json.JSONDecodeError, TypeError):
            return {}


class WorkflowRun(Base):
    """工作流执行实例"""
    __tablename__ = "workflow_runs"

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_PAUSED = "paused"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_ABORTED = "aborted"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("workflow_templates.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True)
    title = Column(String(256), nullable=False)
    status = Column(String(32), default=STATUS_PENDING)
    context = Column(Text, default="{}")
    trigger_source = Column(String(32), default="ai")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def get_context(self):
        try:
            return json.loads(self.context) if self.context else {}
        except (json.JSONDecodeError, TypeError):
            return {}


class WorkflowNodeRun(Base):
    """节点执行记录"""
    __tablename__ = "workflow_node_runs"

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_AWAITING_CONFIRM = "awaiting_confirm"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False, index=True)
    node_id = Column(String(64), nullable=False)
    node_name = Column(String(128), default="")
    action_type = Column(String(64), nullable=False)
    payload = Column(Text, default="{}")
    status = Column(String(32), default=STATUS_PENDING)
    result = Column(Text, default="")
    requires_confirm = Column(Boolean, default=False)
    pending_action_id = Column(Integer, nullable=True)
    retry_count = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())

    def get_payload(self):
        try:
            return json.loads(self.payload) if self.payload else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_result(self):
        try:
            return json.loads(self.result) if self.result else {}
        except (json.JSONDecodeError, TypeError):
            return {}


# ─── 智能体编排工作流平台（Coze 风格）：编排定义 / 执行实例 / 节点执行 ───
class AgentWorkflow(Base):
    """智能体工作流编排定义（可视化画布拖拽生成）"""
    __tablename__ = "agent_workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    category = Column(String(64), default="generic")
    nodes = Column(Text, default="[]")
    edges = Column(Text, default="[]")
    inputs_schema = Column(Text, default="[]")
    outputs_schema = Column(Text, default="[]")
    enabled = Column(Boolean, default=True)
    published = Column(Boolean, default=False)
    trigger_type = Column(String(32), default="manual")
    trigger_condition = Column(Text, default="{}")
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def get_nodes(self):
        try:
            return json.loads(self.nodes) if self.nodes else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_edges(self):
        try:
            return json.loads(self.edges) if self.edges else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_inputs_schema(self):
        try:
            return json.loads(self.inputs_schema) if self.inputs_schema else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_outputs_schema(self):
        try:
            return json.loads(self.outputs_schema) if self.outputs_schema else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_trigger_condition(self):
        """告警触发条件（JSON）。空/非法返回 {}（= 匹配所有告警）。"""
        try:
            return json.loads(self.trigger_condition) if self.trigger_condition else {}
        except (json.JSONDecodeError, TypeError):
            return {}


class AgentWorkflowRun(Base):
    """智能体工作流执行实例"""
    __tablename__ = "agent_workflow_runs"

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_AWAITING_CONFIRM = "awaiting_confirm"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_ABORTED = "aborted"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("agent_workflows.id"), nullable=True)
    workflow_snapshot = Column(Text, default="{}")
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True)
    status = Column(String(32), default=STATUS_PENDING)
    inputs = Column(Text, default="{}")
    runtime_context = Column(Text, default="{}")
    outputs = Column(Text, default="{}")
    trigger_source = Column(String(32), default="api")
    error = Column(Text, default="")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
    triggered_by = Column(String(64), default="")

    def get_workflow_snapshot(self):
        try:
            return json.loads(self.workflow_snapshot) if self.workflow_snapshot else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_inputs(self):
        try:
            return json.loads(self.inputs) if self.inputs else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_runtime_context(self):
        try:
            return json.loads(self.runtime_context) if self.runtime_context else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_outputs(self):
        try:
            return json.loads(self.outputs) if self.outputs else {}
        except (json.JSONDecodeError, TypeError):
            return {}


class AgentWorkflowNodeRun(Base):
    """智能体工作流节点执行记录"""
    __tablename__ = "agent_workflow_node_runs"

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_AWAITING_CONFIRM = "awaiting_confirm"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("agent_workflow_runs.id"), nullable=False, index=True)
    node_id = Column(String(64), nullable=False)
    node_type = Column(String(32), nullable=False)
    node_name = Column(String(128), default="")
    run_config = Column(Text, default="{}")
    status = Column(String(32), default=STATUS_PENDING)
    output = Column(Text, default="{}")
    error = Column(Text, default="")
    requires_confirm = Column(Boolean, default=False)
    pending_action_id = Column(Integer, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())

    def get_config(self):
        try:
            return json.loads(self.run_config) if self.run_config else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_output(self):
        try:
            return json.loads(self.output) if self.output else {}
        except (json.JSONDecodeError, TypeError):
            return {}


class WorkflowAuditLog(Base):
    """智能体工作流操作审计日志（不可抵赖）"""
    __tablename__ = "workflow_audit_logs"

    ACTION_RUN_START = "run_start"
    ACTION_NODE_AUTO_EXEC = "node_auto_exec"
    ACTION_NODE_CONFIRM = "node_confirm"
    ACTION_NODE_CANCEL = "node_cancel"
    ACTION_RUN_ABORT = "run_abort"
    ACTION_NODE_RETRY = "node_retry"
    ACTION_NODE_FORCE_CONFIRM = "node_force_confirm"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, nullable=True, index=True)
    node_run_id = Column(Integer, nullable=True)
    workflow_id = Column(Integer, nullable=True)
    action = Column(String(32), nullable=False)
    operator = Column(String(64), default="")
    tool_name = Column(String(64), default="")
    execution_mode = Column(String(16), default="")
    risk_level = Column(String(16), default="")
    detail = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now())


# ─── Ansible 运维操作：主机清单 / Playbook 模板 / 执行历史 ───
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


# ─── 移动端：设备注册 / 推送审计 / 现场签到 ───
class MobileDevice(Base):
    """移动端设备注册（绑定用户+设备，存推送 token 与生物识别 token）"""
    __tablename__ = "mobile_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id = Column(String(128), nullable=False)
    platform = Column(String(16), nullable=False)
    push_token = Column(String(256))
    biometric_token = Column(String(512))
    app_version = Column(String(32))
    last_active_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "device_id", name="uq_user_device"),)


class PushRecord(Base):
    """推送记录（审计 + 重试依据）"""
    __tablename__ = "push_records"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("mobile_devices.id"), nullable=False)
    title = Column(String(128), nullable=False)
    body = Column(Text)
    payload = Column(Text)
    type = Column(String(32))
    ref_id = Column(Integer)
    status = Column(String(16), default="pending")
    provider_msg_id = Column(String(128))
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime)


# ══════════════════════════════════════════════════════════════
# 智能巡检模块
# ══════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════
# 智能指标推荐
# ══════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════
# 资产基线安全
# ══════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════
# 知识自动沉淀
# ══════════════════════════════════════════════════════════════

class KnowledgeDraft(Base):
    __tablename__ = "knowledge_drafts"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True, index=True)
    title = Column(String(256), nullable=False)
    symptom = Column(Text, default="")
    root_cause = Column(Text, default="")
    solution = Column(Text, default="")
    tags = Column(String(256), default="")
    severity = Column(String(32), default="warning")
    asset_type = Column(String(32), default="")
    source_data = Column(Text, default="")
    source_type = Column(String(32), default="auto")
    sop_steps = Column(Text, default="[]")
    status = Column(String(16), default="pending")
    reject_reason = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


# ══════════════════════════════════════════════════════════════
# 自愈效果追踪 (新结构)
# ══════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════
# Agent 评估体系
# ══════════════════════════════════════════════════════════════

class AgentEvaluation(Base):
    __tablename__ = "agent_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, nullable=True, index=True)
    provider_id = Column(Integer, nullable=True, index=True)
    model_name = Column(String(64), default="")
    task_type = Column(String(32), default="chat")
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    round_count = Column(Integer, default=0)
    tool_call_count = Column(Integer, default=0)
    is_success = Column(Boolean, default=True)
    has_hallucination = Column(Boolean, default=False)
    completion_rate = Column(Float, default=1.0)
    feedback = Column(String(16), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(), index=True)


# ══════════════════════════════════════════════════════════════
# A/B 测试框架
# ══════════════════════════════════════════════════════════════

class ABTestConfig(Base):
    __tablename__ = "ab_test_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    provider_a_id = Column(Integer, ForeignKey("ai_providers.id"), nullable=True)
    provider_b_id = Column(Integer, ForeignKey("ai_providers.id"), nullable=True)
    model_a = Column(String(64), default="")
    model_b = Column(String(64), default="")
    split_ratio = Column(String(8), default="50/50")
    metric = Column(String(32), default="latency")
    status = Column(String(16), default="active")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class ABTestRecord(Base):
    __tablename__ = "ab_test_records"

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("ab_test_configs.id"), nullable=True, index=True)
    session_id = Column(Integer, nullable=True, index=True)
    group = Column(String(8), default="a")
    provider_id = Column(Integer, nullable=True, index=True)
    model_name = Column(String(64), default="")
    latency_ms = Column(Integer, default=0)
    token_count = Column(Integer, default=0)
    is_success = Column(Boolean, default=True)
    user_feedback = Column(String(16), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(), index=True)


# ══════════════════════════════════════════════════════════════
# 异常检测基准评估
# ══════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════
# 资产自动发现
# ══════════════════════════════════════════════════════════════

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

# ══════════════════════════════════════════════════════════════
# 多租户模块
# ══════════════════════════════════════════════════════════════

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, unique=True)
    code = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(16), default="active")
    quota_assets = Column(Integer, default=1000)
    quota_users = Column(Integer, default=50)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class AgentGroundTruth(Base):
    """Agent 评估 GroundTruth 测试集"""
    __tablename__ = "agent_ground_truths"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    category = Column(String(32), default="qa")           # qa / tool_call / rag / reasoning
    question = Column(Text, nullable=False)
    expected_answer = Column(Text, default="")
    expected_tools = Column(Text, default="[]")           # JSON array of expected tool names
    tags = Column(String(256), default="")
    difficulty = Column(String(16), default="medium")     # easy / medium / hard
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class AgentGroundTruthRun(Base):
    """GroundTruth 测试执行记录"""
    __tablename__ = "agent_ground_truth_runs"

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("agent_ground_truths.id"), nullable=False, index=True)
    session_id = Column(Integer, nullable=True)
    provider_id = Column(Integer, nullable=True)
    model_name = Column(String(64), default="")
    actual_answer = Column(Text, default="")
    actual_tools = Column(Text, default="[]")
    answer_score = Column(Float, default=0.0)             # 语义相似度 0~1
    tool_score = Column(Float, default=0.0)               # 工具调用匹配度 0~1
    total_score = Column(Float, default=0.0)              # 综合评分
    latency_ms = Column(Integer, default=0)
    error = Column(String(512), default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


# ─── P2 任务#11: 审计日志（写操作自动记录）──
class AuditLog(Base):
    """审计日志表：所有写操作（POST/PUT/PATCH/DELETE）由中间件自动记录。

    覆盖：资产变更 / 审批 / 配置修改 / 脚本执行 / Token 管理 / 用户权限变更 等。
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String(64), default="")
    method = Column(String(16), nullable=False)           # GET / POST / PUT / PATCH / DELETE
    path = Column(String(256), nullable=False, index=True)        # 实际请求路径（含资源 ID，如 /api/tags/5）
    route_path = Column(String(256), default="", index=True)      # 路由模板路径（如 /api/tags/{tag_id}），用于覆盖率精确匹配
    action = Column(String(64), default="")               # create / update / delete / approve / login 等
    target_type = Column(String(64), default="")          # asset / incident / user / config / token 等
    target_id = Column(String(64), default="")            # 目标资源 ID（字符串以兼容 UUID）
    status_code = Column(Integer, default=0)              # HTTP 响应状态码
    ip = Column(String(64), default="")
    user_agent = Column(String(256), default="")
    request_body = Column(Text, default="")               # 请求体（脱敏后，密码字段已屏蔽）
    response_summary = Column(String(256), default="")    # 响应摘要
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(), index=True)


# ─── P2: Edge Agent 反向隧道 ──────────────────────────────
class EdgeSession(Base):
    """Edge Agent 反向隧道会话。

    edge agent 启动时主动 WebSocket 拨出到云端，云端为此连接创建一个 EdgeSession。
    云端通过 EdgeSession.id 路由 WebSSH / 命令执行到对应 edge agent。
    主机侧零监听端口，所有命令走已建立的反向隧道。
    """
    __tablename__ = "edge_sessions"

    STATUS_ONLINE = "online"
    STATUS_OFFLINE = "offline"
    STATUS_RECONNECTING = "reconnecting"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String(64), unique=True, nullable=False, index=True)  # edge agent 唯一标识（主机名+MAC 哈希）
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)       # 关联资产（首次连接时绑定）
    hostname = Column(String(128), default="")
    os_type = Column(String(32), default="linux")                            # linux / windows / macos
    ip_addresses = Column(Text, default="[]")                                # JSON 数组
    agent_version = Column(String(32), default="")
    status = Column(String(16), default=STATUS_OFFLINE)
    tunnel_token = Column(String(128), default="")                           # 隧道认证 token（edge agent 拨出时携带）
    last_heartbeat_at = Column(DateTime, nullable=True)
    connected_at = Column(DateTime, nullable=True)
    disconnected_at = Column(DateTime, nullable=True)
    reconnect_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def get_ip_addresses(self):
        try:
            return json.loads(self.ip_addresses) if self.ip_addresses else []
        except (json.JSONDecodeError, TypeError):
            return []


class DiagnosisReport(Base):
    """诊断报告 —— 自愈流程的"证据链"，记录自动诊断阶段执行的只读命令及输出."""
    __tablename__ = "diagnosis_reports"

    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True, index=True)
    metric_name = Column(String(100), default="")
    commands_run = Column(Text, default="[]")     # JSON: [{cmd, desc, output, duration_ms, exit_code, tool_id, round_num}]
    raw_output = Column(Text, default="")          # 拼接后的完整输出（供 AI prompt 注入）
    summary = Column(String(500), default="")      # 一句话摘要（可选，后期可由 AI 生成）
    status = Column(String(20), default=STATUS_RUNNING)
    round_num = Column(Integer, default=0)         # 诊断轮次：0=静态初诊，1..N=AI 驱动补诊轮次
    created_at = Column(DateTime, default=lambda: datetime.now(), index=True)
    finished_at = Column(DateTime, nullable=True)


class EdgeCommandLog(Base):
    """Edge Agent 命令执行审计日志（全程审计）。"""
    __tablename__ = "edge_command_logs"

    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_TIMEOUT = "timeout"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("edge_sessions.id"), nullable=False, index=True)
    user_id = Column(Integer, nullable=True)                                 # 发起用户
    username = Column(String(64), default="")
    command = Column(Text, default="")                                       # 执行的命令
    cwd = Column(String(256), default="")                                    # 工作目录
    exit_code = Column(Integer, nullable=True)
    stdout = Column(Text, default="")
    stderr = Column(Text, default="")
    duration_ms = Column(Integer, default=0)
    status = Column(String(16), default=STATUS_RUNNING)
    client_ip = Column(String(64), default="")                               # 发起端 IP（浏览器侧）
    created_at = Column(DateTime, default=lambda: datetime.now(), index=True)
    finished_at = Column(DateTime, nullable=True)


class SandboxConfig(Base):
    """AI 运维沙盒全局配置（单行）。

    用于控制 AI Agent 在节点上的作用范围。本模块独立，
    暂不侵入 agent_service / remediation_service / edge_tunnel_service 现有执行链。
    """
    __tablename__ = "sandbox_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), default="default")
    is_enabled = Column(Boolean, default=False)                              # 沙盒总开关（默认关闭）
    dry_run_mode = Column(Boolean, default=False)                            # 干运行模式：记录但不执行
    max_actions_per_session = Column(Integer, default=10)                    # 单会话最大执行次数
    max_actions_per_day = Column(Integer, default=50)                        # 单日最大执行次数
    max_risk_level = Column(String(16), default="critical")                  # 允许最大风险等级
    execution_window_start = Column(String(5), default="")                   # 写操作允许开始 "HH:MM"
    execution_window_end = Column(String(5), default="")                     # 写操作允许结束 "HH:MM"
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class SandboxPolicy(Base):
    """AI 运维沙盒细粒度策略。

    按作用范围（global/role/user/session）限定 AI Agent 可操作的资产、工具、命令、风险等级、执行配额。
    黑名单优先级高于白名单。
    """
    __tablename__ = "sandbox_policies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)
    description = Column(Text, default="")
    scope_type = Column(String(16), default="global")                        # global / role / user / session
    scope_id = Column(Integer, default=0)
    allowed_asset_ids = Column(Text, default="[]")                           # JSON 数组
    blocked_asset_ids = Column(Text, default="[]")                           # JSON 数组
    allowed_tools = Column(Text, default="[]")                               # JSON 数组
    blocked_tools = Column(Text, default="[]")                               # JSON 数组
    allowed_commands = Column(Text, default="[]")                            # JSON 数组（命令前缀白名单）
    blocked_commands = Column(Text, default="[]")                            # JSON 数组（支持正则）
    max_risk_level = Column(String(16), default="critical")
    max_actions_per_day = Column(Integer, default=0)                         # 0=继承全局
    require_second_approval = Column(Boolean, default=False)                 # 高危操作是否需二级审批
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def get_allowed_asset_ids(self):
        return self._parse_json(self.allowed_asset_ids)

    def get_blocked_asset_ids(self):
        return self._parse_json(self.blocked_asset_ids)

    def get_allowed_tools(self):
        return self._parse_json(self.allowed_tools)

    def get_blocked_tools(self):
        return self._parse_json(self.blocked_tools)

    def get_allowed_commands(self):
        return self._parse_json(self.allowed_commands)

    def get_blocked_commands(self):
        return self._parse_json(self.blocked_commands)

    @staticmethod
    def _parse_json(raw):
        try:
            return json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            return []


class SandboxExecutionLog(Base):
    """AI 运维沙盒执行日志（模拟 vs 真实，全程审计）。"""
    __tablename__ = "sandbox_execution_logs"

    MODE_DRY_RUN = "dry_run"
    MODE_LIVE = "live"
    DECISION_ALLOWED = "allowed"
    DECISION_REJECTED = "rejected"
    DECISION_DRY_RUN = "dry_run"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, default=0)                                  # 关联会话 ID
    action_type = Column(String(32), default="")                             # restart/clean/scale/script/run_command
    tool_name = Column(String(64), default="")                               # MCP 工具名
    asset_id = Column(Integer, default=0)                                    # 目标资产 ID
    risk_level = Column(String(16), default="medium")
    mode = Column(String(8), default=MODE_LIVE)                              # dry_run / live
    payload = Column(Text, default="{}")                                     # 动作参数（JSON）
    decision = Column(String(16), default=DECISION_ALLOWED)                  # allowed / rejected / dry_run
    reject_reason = Column(String(255), default="")
    approved_by = Column(Integer, default=0)                                 # 审批人 ID
    created_at = Column(DateTime, default=lambda: datetime.now(), index=True)


class AutonomousCycle(Base):
    """自主 AI Agent 巡检闭环记录。"""
    __tablename__ = "autonomous_cycles"

    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_PARTIAL = "partial"

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(String(36), default=lambda: str(uuid.uuid4()), index=True)
    status = Column(String(16), default=STATUS_RUNNING)
    phase = Column(String(16), default="perceive")  # perceive / analyze / act / verify
    summary = Column(String(500), default="")
    detail = Column(Text, default="")
    issues_found = Column(Text, default="[]")        # JSON: [{asset_id, metric, severity, description}]
    actions_taken = Column(Text, default="[]")        # JSON: [{action_type, asset_id, command, result, success}]
    llm_analysis = Column(Text, default="")           # LLM 原始分析输出
    error_message = Column(String(500), default="")
    asset_count = Column(Integer, default=0)
    issue_count = Column(Integer, default=0)
    action_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(), index=True)
    finished_at = Column(DateTime, nullable=True)


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


# ==================== 离线部署（Offline Repo）模型 ====================
# 契约见 CONTRACT.md 第十二章。对标 Pixiu `builder serve`：离线包 → 私有 Registry + Apt/Yum 源

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


# ==================== K8S 离线集群部署模型 ====================
# 契约见 CONTRACT.md 第十三章。对标 Pixiu 一键建集群：离线仓库 + kubeadm 编排 + 自动接入监控

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
    nodes_json = Column(Text, default="[]")  # 节点定义（见 CONTRACT 13.3）
    status = Column(String(32), default="draft")
    current_step = Column(Integer, default=0)
    logs_json = Column(Text, default="[]")  # 执行日志事件列表
    kubeconfig = Column(Text, default="")  # 敏感：产出 kubeconfig
    join_token = Column(Text, default="")  # 敏感：worker 加入 token（临时）
    report_json = Column(Text, default="{}")  # 部署报告
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


class AIInsightRecord(Base):
    """AI 分析历史记录沉淀 - 跨指标/日志/链路三页"""
    __tablename__ = "ai_insight_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, default=0)
    source_type = Column(String(16), nullable=False, index=True)  # metrics / logs / traces
    title = Column(String(256), default="")
    question = Column(Text, default="")
    analysis = Column(Text, default="")
    meta_json = Column(Text, default="{}")  # {provider, metric_count, source_name, trend_data, etc}
    provider = Column(String(64), default="")
    score = Column(Integer, default=0)  # 0-100 AI 自评分数
    created_at = Column(DateTime, default=lambda: datetime.now())


class Skill(Base):
    """技能(SKILL.md)注册表 - 对齐 Ongrid internal/skill + biz/skill(F1)。"""
    __tablename__ = "skills"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)  # frontmatter.name, use_skill 入参名
    description = Column(String(512), default="")
    version = Column(String(32), default="1.0.0")
    author = Column(String(128), default="")
    license = Column(String(64), default="")
    category = Column(String(64), default="")
    risk_level = Column(String(32), default="read_only")  # read_only / interactive / danger
    keywords = Column(Text, default="[]")      # JSON list
    tools_required = Column(Text, default="[]")  # JSON list of MCP tool names
    content = Column(Text, default="")          # SKILL.md 全文(frontmatter + 正文)
    source = Column(String(32), default="builtin")  # builtin / upload / marketplace
    file_path = Column(String(512), default="")     # builtin 相对路径
    enabled = Column(Boolean, default=True)
    usage_count = Column(Integer, default=0)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class SkillExecution(Base):
    """技能执行审计 - use_skill/manual 触发记录(F1 可审计执行)。"""
    __tablename__ = "skill_executions"
    id = Column(Integer, primary_key=True, index=True)
    skill_id = Column(Integer, index=True)
    skill_name = Column(String(128), default="", index=True)
    tool = Column(String(64), default="use_skill")  # use_skill / manual
    status = Column(String(16), default="success")  # success / failed
    input_summary = Column(Text, default="")
    output_summary = Column(Text, default="")
    duration_ms = Column(Integer, default=0)
    executed_by = Column(Integer, nullable=True)
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



