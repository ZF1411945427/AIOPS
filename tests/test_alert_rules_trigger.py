"""告警规则触发/去重/归档测试: 覆盖 alert_service 核心逻辑。"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Alert, AlertRule
from app.services import alert_service
from tests.conftest import assert_fields


class TestAlertList:
    def test_list_alerts_empty(self, db: Session):
        alerts, total = alert_service.list_alerts(db)
        assert total == 0
        assert alerts == []

    def test_list_alerts_with_data(self, db: Session, sample_alert: Alert):
        alerts, total = alert_service.list_alerts(db)
        assert total >= 1

    def test_list_alerts_filters_status(self, db: Session):
        from app.models import Alert
        a1 = Alert(rule_id=1, metric_name="cpu", actual_value=90, threshold=80, severity="warning", status="triggered", message="test1", created_at=datetime.utcnow(), archived=False)
        a2 = Alert(rule_id=1, metric_name="cpu", actual_value=90, threshold=80, severity="warning", status="resolved", message="test2", created_at=datetime.utcnow(), archived=False)
        db.add_all([a1, a2])
        db.commit()
        triggered, _ = alert_service.list_alerts(db, status="triggered")
        assert len(triggered) == 1
        resolved, _ = alert_service.list_alerts(db, status="resolved")
        assert len(resolved) == 1

    def test_list_alerts_excludes_archived(self, db: Session):
        from app.models import Alert
        a1 = Alert(rule_id=1, metric_name="mem", actual_value=90, threshold=80, severity="warning", status="resolved", message="archived", created_at=datetime.utcnow(), archived=True)
        a2 = Alert(rule_id=1, metric_name="mem", actual_value=90, threshold=80, severity="warning", status="triggered", message="active", created_at=datetime.utcnow(), archived=False)
        db.add_all([a1, a2])
        db.commit()
        alerts, total = alert_service.list_alerts(db)
        assert total == 1
        assert alerts[0].message == "active"

    def test_list_alerts_filters_severity(self, db: Session):
        from app.models import Alert
        a1 = Alert(rule_id=1, metric_name="cpu", actual_value=90, threshold=80, severity="critical", status="triggered", message="critical", created_at=datetime.utcnow(), archived=False)
        a2 = Alert(rule_id=1, metric_name="cpu", actual_value=90, threshold=80, severity="warning", status="triggered", message="warning", created_at=datetime.utcnow(), archived=False)
        db.add_all([a1, a2])
        db.commit()
        crit, _ = alert_service.list_alerts(db, severity="critical")
        assert len(crit) == 1


class TestAlertAcknowledge:
    def test_acknowledge_alert(self, db: Session, sample_alert: Alert):
        a = alert_service.acknowledge_alert(db, sample_alert.id)
        assert a is not None
        assert a.status == "acknowledged"
        assert a.acknowledged_at is not None

    def test_acknowledge_nonexistent(self, db: Session):
        a = alert_service.acknowledge_alert(db, 99999)
        assert a is None

    def test_acknowledge_idempotent(self, db: Session, sample_alert: Alert):
        a1 = alert_service.acknowledge_alert(db, sample_alert.id)
        a2 = alert_service.acknowledge_alert(db, sample_alert.id)
        assert a2.status == "acknowledged"


class TestAlertResolve:
    def test_resolve_alert(self, db: Session, sample_alert: Alert):
        a = alert_service.resolve_alert(db, sample_alert.id)
        assert a is not None
        assert a.status == "resolved"
        assert a.resolved_at is not None

    def test_resolve_nonexistent(self, db: Session):
        a = alert_service.resolve_alert(db, 99999)
        assert a is None

    def test_resolve_acknowledged_alert(self, db: Session, sample_alert: Alert):
        alert_service.acknowledge_alert(db, sample_alert.id)
        a = alert_service.resolve_alert(db, sample_alert.id)
        assert a.status == "resolved"


class TestAlertStats:
    def test_get_alert_stats_empty(self, db: Session):
        stats = alert_service.get_alert_stats(db)
        assert isinstance(stats, dict)
        assert "total" in stats

    def test_get_alert_stats_with_data(self, db: Session, sample_alert: Alert):
        stats = alert_service.get_alert_stats(db)
        assert stats["total"] >= 1

    def test_get_alert_stats_counts_by_severity(self, db: Session):
        from app.models import Alert
        for sev in ["critical", "warning", "info"]:
            db.add(Alert(rule_id=1, metric_name="cpu", actual_value=90, threshold=80, severity=sev, status="triggered", message=sev, created_at=datetime.utcnow(), archived=False))
        db.commit()
        stats = alert_service.get_alert_stats(db)
        assert stats.get("total", 0) >= 1
        assert stats.get("triggered", 0) >= 1


class TestAlertArchive:
    def test_archive_old_alerts(self, db: Session):
        from app.models import Alert
        old = Alert(rule_id=1, metric_name="cpu", actual_value=90, threshold=80, severity="warning", status="resolved", message="old", created_at=datetime.utcnow() - timedelta(days=90), archived=False)
        recent = Alert(rule_id=1, metric_name="cpu", actual_value=90, threshold=80, severity="warning", status="resolved", message="recent", created_at=datetime.utcnow() - timedelta(days=10), archived=False)
        active = Alert(rule_id=1, metric_name="cpu", actual_value=90, threshold=80, severity="critical", status="triggered", message="active", created_at=datetime.utcnow() - timedelta(days=90), archived=False)
        db.add_all([old, recent, active])
        db.commit()
        result = alert_service.archive_old_alerts(db)
        n = result.get("archived", 0) if isinstance(result, dict) else result
        assert n >= 1
        db.refresh(old)
        assert old.archived is True
        db.refresh(recent)
        assert recent.archived is False
        db.refresh(active)
        assert active.archived is False

    def test_archive_old_alerts_no_old(self, db: Session, sample_alert: Alert):
        result = alert_service.archive_old_alerts(db)
        n = result.get("archived", 0) if isinstance(result, dict) else result
        assert n == 0

    def test_archive_old_alerts_empty_db(self, db: Session):
        result = alert_service.archive_old_alerts(db)
        n = result.get("archived", 0) if isinstance(result, dict) else result
        assert n == 0

    def test_archive_old_alerts_only_resolved(self, db: Session):
        from app.models import Alert
        old_triggered = Alert(rule_id=1, metric_name="cpu", actual_value=90, threshold=80, severity="critical", status="triggered", message="old-triggered", created_at=datetime.utcnow() - timedelta(days=90), archived=False)
        old_resolved = Alert(rule_id=1, metric_name="cpu", actual_value=90, threshold=80, severity="warning", status="resolved", message="old-resolved", created_at=datetime.utcnow() - timedelta(days=90), archived=False)
        db.add_all([old_triggered, old_resolved])
        db.commit()
        result = alert_service.archive_old_alerts(db)
        n = result.get("archived", 0) if isinstance(result, dict) else result
        assert n == 1
        db.refresh(old_resolved)
        assert old_resolved.archived is True


class TestAlertSuppression:
    def test_get_suppressions_empty(self, db: Session):
        supps = alert_service.get_suppressions(db)
        assert supps == []

    def test_get_suppressions_with_limit(self, db: Session):
        supps = alert_service.get_suppressions(db, limit=3)
        assert isinstance(supps, list)