import re
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import LogAnomalyRule, Alert, Asset


def check_log_anomalies(db: Session):
    rules = db.query(LogAnomalyRule).filter(LogAnomalyRule.enabled == True).all()
    now = datetime.now()
    new_alerts = []
    for rule in rules:
        since = now - timedelta(minutes=rule.window_minutes)
        log_records = _fetch_logs(db, rule.source, since)
        count = 0
        matched_ids = []
        for rec in log_records:
            msg = rec.get("message", "")
            if rule.keyword and rule.keyword.lower() in msg.lower():
                count += 1
                matched_ids.append(rec.get("id"))
            elif rule.regex_pattern:
                try:
                    if re.search(rule.regex_pattern, msg):
                        count += 1
                        matched_ids.append(rec.get("id"))
                except Exception:
                    pass
        if count >= rule.threshold:
            existing = (
                db.query(Alert)
                .filter(
                    Alert.metric_name == f"log_anomaly_{rule.id}",
                    Alert.status.in_(["triggered", "acknowledged"]),
                )
                .first()
            )
            if not existing:
                alert = Alert(
                    rule_id=None,
                    metric_name=f"log_anomaly_{rule.id}",
                    actual_value=float(count),
                    threshold=float(rule.threshold),
                    severity=rule.severity,
                    status="triggered",
                    message=f"日志异常 [{rule.name}]: {count} 条匹配 (窗口={rule.window_minutes}min, 阈值={rule.threshold})",
                )
                db.add(alert)
                new_alerts.append(alert)
    if new_alerts:
        db.commit()
    return new_alerts


def _fetch_logs(db: Session, source: str, since: datetime):
    if source == "k8s":
        from app.models import K8sEvent
        events = (
            db.query(K8sEvent)
            .filter(K8sEvent.last_seen >= since)
            .all()
        )
        return [{"id": e.id, "message": e.message} for e in events]
    elif source == "metric":
        from app.models import MetricRecord
        records = (
            db.query(MetricRecord)
            .filter(MetricRecord.timestamp >= since)
            .all()
        )
        return [{"id": r.id, "message": f"{r.name}={r.value}"} for r in records]
    return []
