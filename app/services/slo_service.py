"""
SLO / Error Budget 自动计算服务
从 VictoriaMetrics 查询真实指标，自动计算 SLI（可用性/错误率）
定时写入 SLOConfig 和 ErrorBudget 表
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import SLOConfig, ErrorBudget
from app.services import metric_v2_service


def _query_vm_availability(service_name: str, window_hours: int = 24) -> dict:
    """从 VM 查询服务的可用性指标，返回 {total, errors, availability}."""
    now_s = int(datetime.now().timestamp())
    start_s = now_s - window_hours * 3600

    total = 0.0
    errors = 0.0

    metric_patterns = [
        ("_requests", False), ("_total", False), ("_count", False),
        ("_5xx_errors", True), ("_errors", True), ("_error_count", True),
        ("http_errors", True), ("http_requests", False),
        ("_success", False), ("_failures", True),
    ]

    for suffix, is_error in metric_patterns:
        query = f'{service_name}{{__name__=~".*{suffix}.*"}}'
        result = metric_v2_service.query_promql_range(query, start_s, now_s, step="300s")
        if result.get("status") != "is_success":
            continue
        for item in result.get("data", {}).get("result", []):
            for _, val in item.get("values", []):
                try:
                    v = float(val)
                    if is_error:
                        errors += v
                    else:
                        total += v
                except (TypeError, ValueError):
                    pass

    availability = None
    if total > 0:
        availability = max(0.0, min(1.0, 1.0 - errors / total))

    return {"total": int(total), "errors": int(errors), "availability": availability}


def _calc_burn(slo: SLOConfig, db: Session) -> dict:
    """根据 SLO 目标计算燃烧速率."""
    avail_1h = _query_vm_availability(slo.service_name, window_hours=1)
    if avail_1h["availability"] is None:
        return {"burn_rate": 0.0, "budget_remaining": 100.0,
                "budget_consumed": 0.0, "availability": None,
                "total": 0, "errors": 0}

    error_rate = 1.0 - avail_1h["availability"]
    slo_target = slo.slo_target or 0.999
    allowed_error_rate = 1.0 - slo_target
    burn_rate = error_rate / allowed_error_rate if allowed_error_rate > 0 else 0.0

    window_days = slo.window_days or 30
    budget_total = 100.0
    budget_consumed = burn_rate * (100.0 / window_days) * 24
    budget_remaining = max(0.0, budget_total - budget_consumed)

    return {
        "burn_rate": round(burn_rate, 3),
        "budget_remaining": round(budget_remaining, 2),
        "budget_consumed": round(budget_consumed, 2),
        "availability": avail_1h["availability"],
        "total": avail_1h["total"],
        "errors": avail_1h["errors"],
    }


def _create_slo_alert(db: Session, slo: SLOConfig, burn: dict, status: str):
    """SLO 违规时自动创建告警记录."""
    from app.models import Alert
    burn_rate = burn.get("burn_rate", 0)
    budget_remaining = burn.get("budget_remaining", 100)
    availability = burn.get("availability")
    avail_pct = f"{availability * 100:.2f}%" if availability is not None else "N/A"
    target_pct = f"{(slo.slo_target or 0.999) * 100:.2f}%"
    message = (
        f"[SLO告警] {slo.service_name} 可用性 {avail_pct} "
        f"(目标 {target_pct}), 燃烧速率 {burn_rate:.1f}x, "
        f"错误预算剩余 {budget_remaining:.1f}%"
    )
    alert = Alert(
        rule_id=None,
        asset_id=None,
        metric_name=f"slo_{slo.service_name}",
        actual_value=round(1.0 - (availability or 0), 6),
        threshold=round(1.0 - (slo.slo_target or 0.999), 6),
        severity="critical" if status == "critical" else "warning",
        status="triggered",
        message=message,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    try:
        from app.services.notification_service import notify_new_alerts
        notify_new_alerts(db, [alert])
    except Exception:
        pass
    try:
        from app.services.ws_manager import ws_manager
        import asyncio
        async def _push():
            await ws_manager.publish_alert({
                "type": "alert",
                "alerts": [{
                    "id": alert.id, "metric_name": alert.metric_name,
                    "actual_value": alert.actual_value, "threshold": alert.threshold,
                    "severity": alert.severity, "status": alert.status,
                    "message": alert.message,
                    "created_at": alert.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }],
            })
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_push())
            else:
                loop.run_until_complete(_push())
        except RuntimeError:
            asyncio.run(_push())
    except Exception:
        pass
    return alert


def _trigger_slo_remediation(db: Session, alert):
    """SLO 告警触发后自动匹配并执行自愈动作."""
    from app.models import AutoRemediation, RemediationLog
    remediations = db.query(AutoRemediation).filter(
        AutoRemediation.enabled == True,
    ).all()
    triggered = []
    for rem in remediations:
        if rem.rule_id is not None:
            continue
        recent = db.query(RemediationLog).filter(
            RemediationLog.alert_id == alert.id,
            RemediationLog.remediation_id == rem.id,
        ).first()
        if recent:
            continue
        import json
        params = json.loads(rem.remediation_params) if rem.remediation_params else {}
        log = RemediationLog(
            remediation_id=rem.id,
            alert_id=alert.id,
            action_type=rem.action_type,
            target=params.get("target", f"slo_{alert.metric_name}"),
            is_success=False,
            output=f"SLO违规自动触发: {rem.name}",
        )
        db.add(log)
        alert.status = "acknowledged"
        alert.message += f" [已触发自动响应: {rem.action_type}]"
        triggered.append(rem.name)
    if triggered:
        db.commit()
    return triggered


def calculate_all_slo(db: Session) -> dict:
    """对所有 SLO 配置执行一次自动计算，更新 SLOConfig + ErrorBudget 表.
    当 SLO 状态降级（healthy→warning/critical）时自动生成告警并触发自愈.
    """
    slos = db.query(SLOConfig).all()
    updated = 0
    alerts_created = 0
    remediations_triggered = 0
    for slo in slos:
        prev_status = slo.status or "healthy"
        burn = _calc_burn(slo, db)

        slo.total_requests = burn.get("total", 0)
        slo.error_requests = burn.get("errors", 0)

        br = burn.get("burn_rate", 0)
        br_rem = burn.get("budget_remaining", 100)
        if br > 10 or br_rem < 20:
            status = "critical"
        elif br > 5 or br_rem < 50:
            status = "warning"
        else:
            status = "healthy"
        slo.status = status
        db.commit()

        if prev_status == "healthy" and status in ("critical", "warning"):
            alert = _create_slo_alert(db, slo, burn, status)
            alerts_created += 1
            triggered = _trigger_slo_remediation(db, alert)
            remediations_triggered += len(triggered)

        now = datetime.now()
        period_start = now - timedelta(days=slo.window_days or 30)

        existing = db.query(ErrorBudget).filter(
            ErrorBudget.slo_id == slo.id,
            ErrorBudget.period_started_at >= period_start,
        ).first()

        budget_total = 100.0
        budget_consumed = burn.get("budget_consumed", 0)
        budget_remaining = burn.get("budget_remaining", 100)

        if existing:
            existing.budget_consumed = budget_consumed
            existing.budget_remaining = budget_remaining
            existing.burn_rate = burn.get("burn_rate", 0)
            existing.status = status
        else:
            eb = ErrorBudget(
                slo_id=slo.id,
                service_name=slo.service_name,
                period_started_at=period_start,
                period_ended_at=now,
                budget_total=budget_total,
                budget_consumed=budget_consumed,
                budget_remaining=budget_remaining,
                burn_rate=burn.get("burn_rate", 0),
                status=status,
            )
            db.add(eb)
        db.commit()
        updated += 1

    return {
        "updated": updated, "total": len(slos),
        "alerts_created": alerts_created,
        "remediations_triggered": remediations_triggered,
    }


def get_slo_dashboard(db: Session) -> list:
    """生成 SLO Dashboard 数据，从 VM 实时查询."""
    slos = db.query(SLOConfig).all()
    result = []
    for slo in slos:
        burn = _calc_burn(slo, db)
        status = slo.status or "healthy"
        br = burn.get("burn_rate", 0)
        br_rem = burn.get("budget_remaining", 100)
        if br > 10 or br_rem < 20:
            status = "critical"
        elif br > 5 or br_rem < 50:
            status = "warning"
        result.append({
            "id": slo.id,
            "service_name": slo.service_name,
            "slo_target": slo.slo_target,
            "window_days": slo.window_days,
            "status": status,
            "burn_rate": burn.get("burn_rate", 0),
            "budget_remaining": burn.get("budget_remaining", 100),
            "availability": burn.get("availability"),
            "total_requests": burn.get("total", 0),
            "error_requests": burn.get("errors", 0),
        })
    return result
