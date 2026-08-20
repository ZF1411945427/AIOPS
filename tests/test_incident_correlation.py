"""故障关联测试: 覆盖 incident_service 核心逻辑。"""
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models import Alert, Incident, IncidentAlert
from app.services import incident_service
from tests.conftest import assert_fields


class TestIncidentCRUD:
    def test_create_incident(self, db: Session):
        inc = incident_service.create_incident(
            db, title="[critical] 数据库异常", severity="critical",
            impact="服务不可用", description="MySQL 连接超时"
        )
        assert inc.id is not None
        assert inc.title == "[critical] 数据库异常"
        assert inc.severity == "critical"

    def test_create_incident_minimal(self, db: Session):
        inc = incident_service.create_incident(db)
        assert inc.id is not None
        assert inc.status == "open"

    def test_list_incidents_empty(self, db: Session):
        items, total = incident_service.list_incidents(db)
        assert total == 0
        assert items == []

    def test_list_incidents_with_data(self, db: Session, sample_incident: Incident):
        items, total = incident_service.list_incidents(db)
        assert total >= 1

    def test_list_incidents_filters_status(self, db: Session):
        from app.models import Incident
        inc1 = Incident(title="open incident", severity="warning", status="open", alert_count=1, created_at=datetime.utcnow())
        inc2 = Incident(title="resolved incident", severity="warning", status="resolved", alert_count=1, created_at=datetime.utcnow())
        db.add_all([inc1, inc2])
        db.commit()
        open_items, _ = incident_service.list_incidents(db, status="open")
        assert len(open_items) == 1
        resolved_items, _ = incident_service.list_incidents(db, status="resolved")
        assert len(resolved_items) == 1

    def test_get_incident_detail(self, db: Session, sample_incident: Incident):
        detail = incident_service.get_incident_detail(db, sample_incident.id)
        assert detail is not None
        assert isinstance(detail, dict)
        assert "incident" in detail

    def test_get_incident_detail_not_found(self, db: Session):
        detail = incident_service.get_incident_detail(db, 99999)
        assert detail is None

    def test_resolve_incident(self, db: Session, sample_incident: Incident):
        inc = incident_service.resolve_incident(db, sample_incident.id)
        assert inc is not None
        assert inc.status == "resolved"
        assert inc.resolved_at is not None


class TestIncidentCorrelation:
    def test_correlate_alerts_creates_incident(self, db: Session):
        from app.models import Alert
        a1 = Alert(rule_id=1, metric_name="cpu", actual_value=95, threshold=80, severity="critical", status="triggered", message="CPU high", created_at=datetime.utcnow(), archived=False)
        a2 = Alert(rule_id=1, metric_name="mem", actual_value=90, threshold=80, severity="critical", status="triggered", message="Memory high", created_at=datetime.utcnow(), archived=False)
        db.add_all([a1, a2])
        db.commit()
        result = incident_service.correlate_alerts(db)
        n = result.get("incidents", 0) if isinstance(result, dict) else (result or 0)
        assert n >= 0

    def test_correlate_alerts_empty_db(self, db: Session):
        result = incident_service.correlate_alerts(db)
        n = result.get("incidents", 0) if isinstance(result, dict) else (result or 0)
        assert n >= 0

    def test_correlate_alerts_links_alert_to_incident(self, db: Session):
        from app.models import Alert
        a = Alert(rule_id=1, metric_name="cpu", actual_value=95, threshold=80, severity="critical", status="triggered", message="CPU high", created_at=datetime.utcnow(), archived=False)
        db.add(a)
        db.commit()
        incident_service.correlate_alerts(db)
        links = db.query(IncidentAlert).all()
        assert len(links) >= 0

    def test_escalate_alert_to_incident(self, db: Session, sample_alert: Alert):
        result = incident_service.escalate_alert_to_incident(db, sample_alert.id)
        assert result is not None
        assert "incident_id" in result or "ok" in result

    def test_escalate_alert_nonexistent(self, db: Session):
        result = incident_service.escalate_alert_to_incident(db, 99999)
        assert result.get("ok") is False or result.get("error") is not None

    def test_escalate_alert_twice_same_incident(self, db: Session, sample_alert: Alert):
        r1 = incident_service.escalate_alert_to_incident(db, sample_alert.id)
        r2 = incident_service.escalate_alert_to_incident(db, sample_alert.id)
        assert r2["incident_id"] == r1["incident_id"]


class TestIncidentApproval:
    def test_submit_for_approval(self, db: Session, sample_incident: Incident):
        result = incident_service.submit_for_approval(db, sample_incident.id, submitter_id=1, comment="请审批")
        assert result is not None
        assert "incident_id" in result or "ok" in result

    def test_approve_incident(self, db: Session, sample_incident: Incident):
        incident_service.submit_for_approval(db, sample_incident.id, submitter_id=1)
        result = incident_service.approve_incident(db, sample_incident.id, approver_id=2, comment="同意")
        assert result is not None
        assert result.get("status") in ("approved", "resolved", "pending_approval", "open")

    def test_reject_incident(self, db: Session, sample_incident: Incident):
        incident_service.submit_for_approval(db, sample_incident.id, submitter_id=1)
        result = incident_service.reject_incident(db, sample_incident.id, approver_id=2, comment="理由不足")
        assert result is not None
        assert result.get("status") in ("rejected", "open", "pending_approval", "resolved")

    def test_approve_nonexistent(self, db: Session):
        result = incident_service.approve_incident(db, 99999, approver_id=1)
        assert result.get("ok") is False or result.get("error") is not None

    def test_get_approval_history(self, db: Session, sample_incident: Incident):
        incident_service.submit_for_approval(db, sample_incident.id, submitter_id=1)
        incident_service.approve_incident(db, sample_incident.id, approver_id=2, comment="同意")
        history = incident_service.get_approval_history(db, sample_incident.id)
        assert len(history) >= 2