from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import MetricRecord, K8sEvent, Alert


def detect_contention(db: Session):
    now = datetime.now()
    since = now - timedelta(minutes=15)
    new_alerts = []

    oom_events = (
        db.query(K8sEvent)
        .filter(
            K8sEvent.last_seen >= since,
            K8sEvent.reason.ilike("%OOM%"),
        )
        .count()
    )
    if oom_events >= 3:
        existing = db.query(Alert).filter(
            Alert.metric_name == "contention_oom",
            Alert.status.in_(["triggered", "acknowledged"]),
        ).first()
        if not existing:
            new_alerts.append(Alert(
                metric_name="contention_oom",
                actual_value=float(oom_events),
                threshold=3,
                severity="critical",
                status="triggered",
                message=f"集群 OOM 事件频发: 近15分钟 {oom_events} 次",
            ))

    crash_events = (
        db.query(K8sEvent)
        .filter(
            K8sEvent.last_seen >= since,
            K8sEvent.reason.ilike("%CrashLoopBackOff%"),
        )
        .count()
    )
    if crash_events >= 3:
        existing = db.query(Alert).filter(
            Alert.metric_name == "contention_crashloop",
            Alert.status.in_(["triggered", "acknowledged"]),
        ).first()
        if not existing:
            new_alerts.append(Alert(
                metric_name="contention_crashloop",
                actual_value=float(crash_events),
                threshold=3,
                severity="critical",
                status="triggered",
                message=f"集群 CrashLoopBackOff 频发: 近15分钟 {crash_events} 次",
            ))

    node_not_ready = (
        db.query(K8sEvent)
        .filter(
            K8sEvent.last_seen >= since,
            K8sEvent.reason == "NodeNotReady",
        )
        .count()
    )
    if node_not_ready > 0:
        existing = db.query(Alert).filter(
            Alert.metric_name == "contention_node_notready",
            Alert.status.in_(["triggered", "acknowledged"]),
        ).first()
        if not existing:
            new_alerts.append(Alert(
                metric_name="contention_node_notready",
                actual_value=float(node_not_ready),
                threshold=1,
                severity="critical",
                status="triggered",
                message=f"节点不可用: 近15分钟 {node_not_ready} 个 NodeNotReady 事件",
            ))

    if new_alerts:
        for a in new_alerts:
            db.add(a)
        db.commit()
    return new_alerts
