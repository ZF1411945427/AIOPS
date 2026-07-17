import statistics
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import TraceAnomalyConfig, Span, Alert


def check_trace_anomalies(db: Session):
    configs = db.query(TraceAnomalyConfig).filter(TraceAnomalyConfig.enabled == True).all()
    now = datetime.now()
    new_alerts = []
    for cfg in configs:
        window = 5
        since = now - timedelta(minutes=window)
        q = db.query(Span).filter(Span.started_at >= since)
        if cfg.service_name:
            q = q.filter(Span.service_name == cfg.service_name)

        spans = q.all()
        if not spans:
            continue

        total = len(spans)
        errors = [s for s in spans if s.status == "ERROR"]
        error_count = len(errors)
        error_rate = error_count / total if total > 0 else 0

        durations = [s.duration_ms for s in spans if s.duration_ms is not None]
        avg_latency = statistics.mean(durations) if durations else 0
        sorted_dur = sorted(durations)
        p99 = sorted_dur[int(len(sorted_dur) * 0.99)] if sorted_dur else 0

        alerts_fired = []

        if error_rate > cfg.error_rate_threshold:
            metric_name = f"trace_error_rate_{cfg.id}"
            existing = (
                db.query(Alert)
                .filter(
                    Alert.metric_name == metric_name,
                    Alert.status.in_(["triggered", "acknowledged"]),
                )
                .first()
            )
            if not existing:
                alert = Alert(
                    rule_id=None,
                    metric_name=metric_name,
                    actual_value=round(error_rate, 4),
                    threshold=round(cfg.error_rate_threshold, 4),
                    severity="warning",
                    status="triggered",
                    message=f"Trace异常 [{cfg.name}]: {cfg.service_name or '全部服务'} 错误率 {error_rate:.1%} (阈值={cfg.error_rate_threshold:.1%}, {total} spans)",
                )
                db.add(alert)
                alerts_fired.append(alert)

        if avg_latency > cfg.latency_threshold_ms:
            metric_name = f"trace_latency_{cfg.id}"
            existing = (
                db.query(Alert)
                .filter(
                    Alert.metric_name == metric_name,
                    Alert.status.in_(["triggered", "acknowledged"]),
                )
                .first()
            )
            if not existing:
                alert = Alert(
                    rule_id=None,
                    metric_name=metric_name,
                    actual_value=round(avg_latency, 1),
                    threshold=round(cfg.latency_threshold_ms, 1),
                    severity="warning",
                    status="triggered",
                    message=f"Trace异常 [{cfg.name}]: {cfg.service_name or '全部服务'} 平均延迟 {avg_latency:.0f}ms (阈值={cfg.latency_threshold_ms:.0f}ms, P99={p99:.0f}ms)",
                )
                db.add(alert)
                alerts_fired.append(alert)

        new_alerts.extend(alerts_fired)

    if new_alerts:
        db.commit()
    return new_alerts
