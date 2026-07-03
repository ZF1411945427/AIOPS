from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Alert, AlertRule, MetricRecord, AlertSilence, AlertSuppression, AlertEscalation, SystemConfig, NotificationChannel, AlertSilenceSchedule
from app.services import notification_service


def list_rules(db: Session):
    return db.query(AlertRule).order_by(AlertRule.id.desc()).all()


def get_rule(db: Session, rule_id: int):
    return db.query(AlertRule).filter(AlertRule.id == rule_id).first()


def create_rule(db: Session, data: dict):
    rule = AlertRule(**data)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_rule(db: Session, rule_id: int, data: dict):
    rule = get_rule(db, rule_id)
    if not rule:
        return None
    for k, v in data.items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


def delete_rule(db: Session, rule_id: int):
    rule = get_rule(db, rule_id)
    if not rule:
        return False
    db.delete(rule)
    db.commit()
    return True


def get_active_silences(db: Session):
    now = datetime.now()
    return db.query(AlertSilence).filter(AlertSilence.until > now).all()


def create_silence(db: Session, rule_id: int, minutes: int, reason: str = ""):
    until = datetime.now() + timedelta(minutes=minutes)
    silence = AlertSilence(rule_id=rule_id, until=until, reason=reason)
    db.add(silence)
    db.commit()
    db.refresh(silence)
    return silence


def delete_silence(db: Session, silence_id: int):
    db.query(AlertSilence).filter(AlertSilence.id == silence_id).delete()
    db.commit()


def check_rules(db: Session):
    rules = db.query(AlertRule).filter(AlertRule.enabled == True).all()
    now = datetime.now()
    silenced_rule_ids = {
        s.rule_id for s in db.query(AlertSilence).filter(AlertSilence.until > now).all()
    }
    silenced_metric_names = set()
    schedules = db.query(AlertSilenceSchedule).filter(AlertSilenceSchedule.enabled == True).all()
    for s in schedules:
        try:
            import croniter
            cron = croniter.croniter(s.cron_expr, now)
            prev = cron.get_prev(datetime)
            if prev + timedelta(minutes=s.duration_minutes) >= now:
                if s.metric_name:
                    silenced_metric_names.add(s.metric_name)
                if s.rule_id:
                    silenced_rule_ids.add(s.rule_id)
        except Exception:
            pass
    now = datetime.now()
    dedup_window = timedelta(minutes=5)
    storm_window = timedelta(minutes=1)
    storm_threshold = 3

    new_alerts = []
    suppressed = []

    for rule in rules:
        if rule.id in silenced_rule_ids:
            continue

        storm_count = (
            db.query(func.count(Alert.id))
            .filter(Alert.rule_id == rule.id, Alert.created_at > now - storm_window)
            .scalar() or 0
        )
        if storm_count >= storm_threshold:
            sup = db.query(AlertSuppression).filter(
                AlertSuppression.rule_id == rule.id,
                AlertSuppression.reason == "storm",
                AlertSuppression.created_at > now - timedelta(minutes=5),
            ).first()
            if sup:
                sup.suppressed_count += 1
            else:
                db.add(AlertSuppression(rule_id=rule.id, rule_name=rule.name, metric_name=rule.metric_name, reason="storm"))
            db.commit()
            suppressed.append(rule.id)
            continue

        latest = (
            db.query(MetricRecord)
            .filter(MetricRecord.name == rule.metric_name)
            .order_by(MetricRecord.timestamp.desc())
            .first()
        )
        if not latest:
            continue
        triggered = False
        if rule.condition == "gt" and latest.value > rule.threshold:
            triggered = True
        elif rule.condition == "lt" and latest.value < rule.threshold:
            triggered = True
        if triggered:
            active = (
                db.query(Alert)
                .filter(
                    Alert.rule_id == rule.id,
                    Alert.asset_id == latest.asset_id,
                    Alert.status.in_(["triggered", "acknowledged"]),
                )
                .first()
            )
            recent_resolved = (
                db.query(Alert)
                .filter(
                    Alert.rule_id == rule.id,
                    Alert.asset_id == latest.asset_id,
                    Alert.status == "resolved",
                    Alert.created_at > now - dedup_window,
                )
                .first()
            )
            if not active and not recent_resolved:
                alert = Alert(
                    rule_id=rule.id,
                    asset_id=latest.asset_id,
                    metric_name=rule.metric_name,
                    actual_value=latest.value,
                    threshold=rule.threshold,
                    severity=rule.severity,
                    status="triggered",
                    message=f"{rule.name} - {rule.metric_name} 褰撳墠鍊?{latest.value} 瓒呭嚭闃堝€?{rule.threshold}",
                )
                db.add(alert)
                new_alerts.append(alert)
            elif not active and recent_resolved:
                sup = db.query(AlertSuppression).filter(
                    AlertSuppression.rule_id == rule.id,
                    AlertSuppression.reason == "dedup",
                    AlertSuppression.created_at > now - timedelta(hours=1),
                ).first()
                if sup:
                    sup.suppressed_count += 1
                else:
                    db.add(AlertSuppression(rule_id=rule.id, rule_name=rule.name, metric_name=rule.metric_name, reason="dedup"))
                db.commit()
    if new_alerts:
        db.commit()
        for a in new_alerts:
            db.refresh(a)
        notification_service.notify_new_alerts(db, new_alerts)
        try:
            from app.routers.alert_webhooks import call_alert_webhooks
            for a in new_alerts:
                call_alert_webhooks(db, a)
        except Exception:
            pass
    return new_alerts


def get_alert_detail(db: Session, alert_id: int):
    from app.models import Asset
    from app.services.knowledge_graph_service import recommend_kb_for_alert
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return None
    asset = db.query(Asset).filter(Asset.id == alert.asset_id).first()
    recommendations = recommend_kb_for_alert(db, alert)
    escalations = get_escalations_for_alert(db, alert_id)
    return {
        "alert": alert,
        "asset": asset,
        "notification_logs": notification_service.get_notification_logs_for_alert(db, alert_id),
        "recommendations": recommendations,
        "escalations": escalations,
    }


def list_alerts(db: Session, status: str = "", severity: str = "", page: int = 1, per_page: int = 20):
    q = db.query(Alert)
    if status:
        q = q.filter(Alert.status == status)
    if severity:
        q = q.filter(Alert.severity == severity)
    q = q.order_by(Alert.created_at.desc())
    total = q.count()
    alerts = q.offset((page - 1) * per_page).limit(per_page).all()
    return alerts, total


def acknowledge_alert(db: Session, alert_id: int):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return None
    alert.status = "acknowledged"
    db.commit()
    db.refresh(alert)
    return alert


def resolve_alert(db: Session, alert_id: int):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return None
    alert.status = "resolved"
    alert.resolved_at = datetime.now()
    db.commit()
    db.refresh(alert)
    return alert


def get_alert_stats(db: Session):
    total = db.query(func.count(Alert.id)).scalar() or 0
    triggered = db.query(func.count(Alert.id)).filter(Alert.status == "triggered").scalar() or 0
    acknowledged = db.query(func.count(Alert.id)).filter(Alert.status == "acknowledged").scalar() or 0
    resolved = db.query(func.count(Alert.id)).filter(Alert.status == "resolved").scalar() or 0
    suppressed_total = db.query(func.sum(AlertSuppression.suppressed_count)).scalar() or 0
    storm_suppressed = (
        db.query(func.sum(AlertSuppression.suppressed_count))
        .filter(AlertSuppression.reason == "storm")
        .scalar() or 0
    )
    dedup_suppressed = (
        db.query(func.sum(AlertSuppression.suppressed_count))
        .filter(AlertSuppression.reason == "dedup")
        .scalar() or 0
    )
    return {
        "total": total, "triggered": triggered,
        "acknowledged": acknowledged, "resolved": resolved,
        "suppressed_total": suppressed_total,
        "storm_suppressed": storm_suppressed,
        "dedup_suppressed": dedup_suppressed,
    }


def get_suppressions(db: Session, limit: int = 50):
    return db.query(AlertSuppression).order_by(AlertSuppression.created_at.desc()).limit(limit).all()


def batch_acknowledge(db: Session):
    alerts = db.query(Alert).filter(Alert.status == "triggered").all()
    for a in alerts:
        a.status = "acknowledged"
    db.commit()
    return len(alerts)


def batch_resolve(db: Session):
    alerts = db.query(Alert).filter(Alert.status.in_(["triggered", "acknowledged"])).all()
    now = datetime.now()
    for a in alerts:
        a.status = "resolved"
        a.resolved_at = now
    db.commit()
    return len(alerts)


def get_escalation_minutes(db: Session) -> int:
    cfg = db.query(SystemConfig).filter(SystemConfig.key == "escalation_minutes").first()
    try:
        return int(cfg.value) if cfg else 5
    except (ValueError, TypeError):
        return 5


def escalate_alerts(db: Session):
    escalation_minutes = get_escalation_minutes(db)
    now = datetime.now()
    cutoff = now - timedelta(minutes=escalation_minutes)
    old_alerts = (
        db.query(Alert)
        .filter(Alert.status == "triggered", Alert.created_at < cutoff)
        .all()
    )
    promoted = 0
    for a in old_alerts:
        original = a.severity
        if a.severity == "info":
            a.severity = "warning"
        elif a.severity == "warning":
            a.severity = "critical"
        if a.severity != original:
            escalation = AlertEscalation(
                alert_id=a.id,
                from_severity=original,
                to_severity=a.severity,
                reason=f"超时{escalation_minutes}分钟未处理，自动升级",
            )
            db.add(escalation)
            a.message += f" [已升级:{a.severity}]"
            promoted += 1
            _send_escalation_notification(db, a, original)
    if promoted:
        db.commit()
    return promoted


def _send_escalation_notification(db: Session, alert: Alert, from_severity: str):
    from app.services.notification_service import send_notification
    try:
        channels = db.query(NotificationChannel).filter(
            NotificationChannel.enabled == True,
        ).all()
        for ch in channels:
            if alert.severity in (ch.severity or "").split(",") or not ch.severity:
                send_notification(db, alert, ch)
    except Exception:
        pass


def get_escalations_for_alert(db: Session, alert_id: int):
    return db.query(AlertEscalation).filter(AlertEscalation.alert_id == alert_id).order_by(AlertEscalation.created_at).all()


def is_in_silence_window(db: Session, alert: Alert) -> bool:
    from datetime import datetime, timedelta
    now = datetime.now()
    schedules = db.query(AlertSilenceSchedule).filter(AlertSilenceSchedule.enabled == True).all()
    for s in schedules:
        rule_match = (s.rule_id is None or s.rule_id == alert.rule_id)
        metric_match = (s.metric_name == "" or s.metric_name == alert.metric_name)
        if not rule_match or not metric_match:
            continue
        try:
            import croniter
            cron = croniter.croniter(s.cron_expr, now)
            prev = cron.get_prev(datetime)
            if prev + timedelta(minutes=s.duration_minutes) >= now:
                return True
        except Exception:
            pass
    return False


