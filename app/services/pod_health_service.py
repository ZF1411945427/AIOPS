from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import K8sEvent, Alert, Asset


def check_pod_anomalies(db: Session):
    since = datetime.now() - timedelta(minutes=30)
    critical_reasons = [
        "CrashLoopBackOff", "OOMKilling", "Failed", "BackOff",
        "NodeNotReady", "CreateContainerError", "InvalidImageName",
        "NetworkNotReady", "FailedCreatePodSandBox", "ExceededGracePeriod",
    ]
    events = (
        db.query(K8sEvent)
        .filter(
            K8sEvent.last_seen_at >= since,
            K8sEvent.severity.in_(["critical", "warning"]),
        )
        .all()
    )
    new_alerts = []
    for ev in events:
        is_critical = any(r in (ev.reason or "") for r in critical_reasons)
        if not is_critical:
            continue
        existing = (
            db.query(Alert)
            .filter(
                Alert.metric_name == f"pod_anomaly_{ev.kind}",
                Alert.message.like(f"%{ev.name}%"),
                Alert.status.in_(["triggered", "acknowledged"]),
            )
            .first()
        )
        if existing:
            continue
        asset = (
            db.query(Asset)
            .filter(Asset.ci_type == ev.kind.lower(), Asset.name.like(f"%{ev.name}%"))
            .first()
        )
        alert = Alert(
            rule_id=None,
            asset_id=asset.id if asset else None,
            metric_name=f"pod_anomaly_{ev.kind}",
            actual_value=float(ev.count or 1),
            threshold=1,
            severity="critical" if is_critical else "warning",
            status="triggered",
            message=f"Pod异常 [{ev.reason}] {ev.kind}/{ev.name}: {ev.message[:200]}",
        )
        db.add(alert)
        new_alerts.append(alert)
    if new_alerts:
        db.commit()
    return new_alerts


def get_pod_anomalies(db: Session, pod_name: str, limit: int = 10):
    return (
        db.query(K8sEvent)
        .filter(
            K8sEvent.name.ilike(f"%{pod_name}%"),
            K8sEvent.severity.in_(["critical", "warning"]),
        )
        .order_by(K8sEvent.last_seen_at.desc())
        .limit(limit)
        .all()
    )
