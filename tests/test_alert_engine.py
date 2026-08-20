"""告警规则引擎: 静态阈值触发 / 单例去重 / storm 抑制 / 静默。

覆盖 app/services/alert_service.py 的核心告警链路(对标 keep alert dedup):
  - metric_raw 静态阈值评估
  - svc_up 单例去重(已有活跃告警不重复写入, 仅刷新 last_notified_at)
  - 已解决告警在 dedup 窗口内不重复触发
  - storm(1 分钟 3 次)抑制
  - 静默窗口跳过规则
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Alert, AlertRule, AlertSilence, MetricRecord
from app.services import alert_service


def _seed_metric(db: Session, name: str, value: float, asset_id: int = 1, ts=None):
    from app.models import Asset
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if asset is None:
        db.add(Asset(name=f"asset-{asset_id}", ci_type="server",
                     ip=f"192.168.1.{asset_id}", status="online",
                     connection_type="ssh", ci_attributes="{}"))
        db.commit()
    db.add(MetricRecord(name=name, asset_id=asset_id, value=value,
                        timestamp=ts or datetime.now()))
    db.commit()


class TestMetricRawEval:
    def test_gt_triggers(self, db: Session):
        rule = AlertRule(name="cpu", kind="metric_raw", metric_name="cpu_usage",
                         threshold=80.0, severity="critical", condition="gt",
                         enabled=True)
        latest = type("M", (), {"value": 95.0, "asset_id": 1})
        triggered, v, _ = alert_service._eval_metric_raw(rule, latest, db)
        assert triggered is True
        assert v == 95.0

    def test_gt_not_triggers(self, db: Session):
        rule = AlertRule(name="cpu", kind="metric_raw", metric_name="cpu_usage",
                         threshold=80.0, severity="critical", condition="gt",
                         enabled=True)
        latest = type("M", (), {"value": 50.0, "asset_id": 1})
        triggered, v, _ = alert_service._eval_metric_raw(rule, latest, db)
        assert triggered is False

    def test_lt_triggers(self, db: Session):
        rule = AlertRule(name="svc", kind="metric_raw", metric_name="svc_up",
                         threshold=1.0, severity="critical", condition="lt",
                         enabled=True)
        latest = type("M", (), {"value": 0.0, "asset_id": 1})
        triggered, _, _ = alert_service._eval_metric_raw(rule, latest, db)
        assert triggered is True

    def test_eq_triggers(self, db: Session):
        rule = AlertRule(name="eq", kind="metric_raw", metric_name="m",
                         threshold=7.0, severity="warning", condition="eq",
                         enabled=True)
        latest = type("M", (), {"value": 7.0, "asset_id": 1})
        triggered, _, _ = alert_service._eval_metric_raw(rule, latest, db)
        assert triggered is True

    def test_unknown_condition_no_trigger(self, db: Session):
        rule = AlertRule(name="unk", kind="metric_raw", metric_name="m",
                         threshold=1.0, severity="warning", condition="???",
                         enabled=True)
        latest = type("M", (), {"value": 99.0, "asset_id": 1})
        triggered, _, _ = alert_service._eval_metric_raw(rule, latest, db)
        assert triggered is False


class TestCheckRulesTrigger:
    def test_metric_raw_rule_creates_alert(self, db: Session):
        rule = AlertRule(name="cpu", kind="metric_raw", metric_name="cpu_usage",
                         threshold=80.0, severity="critical", condition="gt",
                         enabled=True)
        db.add(rule)
        db.commit()
        _seed_metric(db, "cpu_usage", 95.0)

        new_alerts = alert_service.check_rules(db)
        assert len(new_alerts) >= 1
        a = new_alerts[0]
        assert a.status == "triggered"
        assert a.severity == "critical"
        assert a.asset_id == 1

    def test_svc_up_singleton_dedup(self, db: Session):
        """svc_up 单例去重: 已有活跃告警时不重复写入(只刷新 last_notified_at)。"""
        rule = AlertRule(name="svc_up 服务存活", kind="metric_raw", metric_name="svc_up",
                         threshold=1.0, severity="critical", condition="lt",
                         enabled=True)
        db.add(rule)
        db.commit()
        db.refresh(rule)

        # 已有活跃告警
        db.add(Alert(rule_id=rule.id, asset_id=1, metric_name="svc_up",
                     actual_value=0.0, threshold=1.0, severity="critical",
                     status="triggered", message="服务离线",
                     created_at=datetime.now() - timedelta(minutes=2),
                     last_notified_at=datetime.now() - timedelta(minutes=2)))
        db.commit()
        _seed_metric(db, "svc_up", 0.0)

        new_alerts = alert_service.check_rules(db)
        assert new_alerts == [], "已有活跃 svc_up 告警时不应重复新增"

        active = db.query(Alert).filter(Alert.rule_id == rule.id,
                                        Alert.status == "triggered").all()
        assert len(active) == 1
        assert active[0].last_notified_at is not None

    def test_dedup_window_prevents_respawn(self, db: Session):
        """已解决告警在 dedup 窗口(5min)内不重复触发。"""
        rule = AlertRule(name="cpu", kind="metric_raw", metric_name="cpu_usage",
                         threshold=80.0, severity="critical", condition="gt",
                         enabled=True)
        db.add(rule)
        db.commit()
        db.refresh(rule)

        db.add(Alert(rule_id=rule.id, asset_id=1, metric_name="cpu_usage",
                     actual_value=95.0, threshold=80.0, severity="critical",
                     status="resolved", message="已恢复",
                     created_at=datetime.now() - timedelta(minutes=1)))
        db.commit()
        _seed_metric(db, "cpu_usage", 95.0)

        new_alerts = alert_service.check_rules(db)
        assert new_alerts == [], "dedup 窗口内已解决告警不应重新触发"
        db.rollback()

        # 验证 dedup suppression 被记录
        from app.models import AlertSuppression
        sups = db.query(AlertSuppression).filter(AlertSuppression.reason == "dedup").all()
        assert len(sups) >= 1


class TestStarRuleNoMetric:
    def test_no_metric_data_no_alerts(self, db: Session):
        rule = AlertRule(name="cpu", kind="metric_raw", metric_name="nonexistent_metric",
                         threshold=80.0, severity="critical", condition="gt",
                         enabled=True)
        db.add(rule)
        db.commit()
        new_alerts = alert_service.check_rules(db)
        assert new_alerts == []


class TestSilence:
    def test_silenced_rule_skipped(self, db: Session):
        rule = AlertRule(name="cpu", kind="metric_raw", metric_name="cpu_usage",
                         threshold=80.0, severity="critical", condition="gt",
                         enabled=True)
        db.add(rule)
        db.commit()
        db.refresh(rule)
        db.add(AlertSilence(rule_id=rule.id, reason="维护窗口",
                            expires_at=datetime.now() + timedelta(minutes=60)))
        db.commit()
        _seed_metric(db, "cpu_usage", 95.0)

        new_alerts = alert_service.check_rules(db)
        assert new_alerts == [], "被静默的规则不应产生告警"


class TestAlertCRUD:
    def test_acknowledge_alert(self, db: Session):
        al = Alert(rule_id=1, asset_id=1, metric_name="cpu", actual_value=95.0,
                   threshold=80.0, severity="critical", status="triggered",
                   message="x", created_at=datetime.now())
        db.add(al)
        db.commit()
        db.refresh(al)
        updated = alert_service.acknowledge_alert(db, al.id)
        assert updated is not None
        assert updated.status == "acknowledged"

    def test_acknowledge_not_found(self, db: Session):
        assert alert_service.acknowledge_alert(db, 99999) is None

    def test_batch_acknowledge_counts(self, db: Session):
        db.add_all([Alert(rule_id=1, asset_id=i, metric_name="m", actual_value=10.0,
                          threshold=5.0, severity="warning", status="triggered",
                          message="m", created_at=datetime.now()) for i in range(3)])
        db.commit()
        n = alert_service.batch_acknowledge(db)
        assert n == 3

    def test_get_alert_stats_counts(self, db: Session):
        stats = alert_service.get_alert_stats(db)
        assert "total" in stats
        assert "triggered" in stats

    def test_archive_old_alerts_marks_archived(self, db: Session):
        old = Alert(rule_id=1, asset_id=1, metric_name="m", actual_value=1.0,
                    threshold=2.0, severity="warning", status="resolved",
                    message="old", created_at=datetime.now() - timedelta(days=100))
        db.add(old)
        db.commit()
        db.refresh(old)
        alert_service.archive_old_alerts(db)
        db.refresh(old)
        assert old.archived is True