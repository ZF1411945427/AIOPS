"""域模型: alert (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""

import json

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint

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
