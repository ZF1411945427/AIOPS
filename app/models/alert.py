"""域模型: alert (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""


from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text

from app.database import Base


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
    archived = Column(Boolean, default=False)          # 归档标记：超保留期的已解决告警
    last_notified_at = Column(DateTime, nullable=True)  # 最近一次通知/推送时间（供周期提醒刷新，不新增记录）
    source = Column(String(32), default="internal")    # 告警来源：internal / 入站源名 / remote_write


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


class AlertCluster(Base):
    """第二十四章：告警关联落库持久化（告警聚类快照 + 自动生成 incident 闭环）。

    cluster_id: 聚类键（svc-<id> / time-<n> / topo-<id>）
    incident_id: 自动生成的故障单（满足条件时回填）
    """
    __tablename__ = "alert_clusters"

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(String(64), nullable=False, index=True)
    cluster_type = Column(String(32), default="service")  # service / time_window / topology
    alert_ids_json = Column(Text, default="[]")
    key_asset_id = Column(Integer, nullable=True)
    alert_count = Column(Integer, default=0)
    dominant_severity = Column(String(32), default="info")
    summary_json = Column(Text, default="{}")
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())

    def get_alert_ids(self):
        import json
        try:
            return json.loads(self.alert_ids_json) if self.alert_ids_json else []
        except Exception:
            return []

    def get_summary(self):
        import json
        try:
            return json.loads(self.summary_json) if self.summary_json else {}
        except Exception:
            return {}


class InboundSource(Base):
    """第二十三章：外部告警入站告警源（对接 Alertmanager / remote_write / webhook / Datadog / PagerDuty）。"""
    __tablename__ = "inbound_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, unique=True)
    source_type = Column(String(32), default="alertmanager")
    endpoint_token = Column(String(64), default="")
    labels_json = Column(Text, default="{}")
    metrics_to_rules = Column(Text, default="{}")
    auto_create_rule = Column(Boolean, default=False)
    status_webhook_url = Column(String(512), default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())

    def get_labels(self):
        import json
        try:
            return json.loads(self.labels_json) if self.labels_json else {}
        except Exception:
            return {}

    def get_metrics_to_rules(self):
        import json
        try:
            return json.loads(self.metrics_to_rules) if self.metrics_to_rules else {}
        except Exception:
            return {}
