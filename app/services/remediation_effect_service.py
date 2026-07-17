import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, Integer, Float
from app.models import RemediationEffectRecord, RemediationLog, Alert, Asset, AutoRemediation


def track_effect(log_id: int, db: Session) -> dict:
    """追踪单次自愈执行的效果：执行后检查告警状态，记录到 RemediationEffectRecord"""
    log = db.query(RemediationLog).filter(RemediationLog.id == log_id).first()
    if not log:
        return {"ok": False, "error": "执行记录不存在"}

    alert = db.query(Alert).filter(Alert.id == log.alert_id).first() if log.alert_id else None
    asset = db.query(Asset).filter(Asset.id == log.asset_id).first() if log.asset_id else None

    effect_value = "no_change"
    status_before = "triggered"
    status_after = "unknown"
    notes = ""

    if alert:
        status_before = alert.status or "triggered"
        if alert.status == "resolved":
            effect_value = "resolved"
            status_after = "resolved"
            notes = f"告警 {alert.id} 已解决"
        elif alert.status == "acknowledged":
            effect_value = "improved"
            status_after = "acknowledged"
            notes = f"告警 {alert.id} 已确认"
        else:
            effect_value = "no_change"
            status_after = alert.status or "triggered"
            notes = f"告警 {alert.id} 状态: {alert.status}"

    rec = RemediationEffectRecord(
        remediation_id=log.remediation_id,
        log_id=log_id,
        alert_id=log.alert_id,
        asset_id=alert.asset_id if alert else None,
        status_before=status_before,
        status_after=status_after,
        effect=effect_value,
        checked_at=datetime.now(),
        description=notes,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return {"ok": True, "effect_id": rec.id, "effect": effect_value, "notes": notes}


def get_effect_stats(db: Session, days: int = 30) -> dict:
    since = datetime.now() - timedelta(days=days)

    total = db.query(func.count(RemediationEffectRecord.id)).filter(
        RemediationEffectRecord.created_at >= since,
    ).scalar() or 0

    resolved = db.query(func.count(RemediationEffectRecord.id)).filter(
        RemediationEffectRecord.created_at >= since,
        RemediationEffectRecord.effect == "resolved",
    ).scalar() or 0

    improved = db.query(func.count(RemediationEffectRecord.id)).filter(
        RemediationEffectRecord.created_at >= since,
        RemediationEffectRecord.effect == "improved",
    ).scalar() or 0

    no_change = db.query(func.count(RemediationEffectRecord.id)).filter(
        RemediationEffectRecord.created_at >= since,
        RemediationEffectRecord.effect == "no_change",
    ).scalar() or 0

    worsened = db.query(func.count(RemediationEffectRecord.id)).filter(
        RemediationEffectRecord.created_at >= since,
        RemediationEffectRecord.effect == "worsened",
    ).scalar() or 0

    success_rate = round(resolved / max(total, 1) * 100, 1)
    improve_rate = round((resolved + improved) / max(total, 1) * 100, 1)

    rem_list = db.query(AutoRemediation).filter(AutoRemediation.enabled == True).all()
    rem_stats = []
    for rem in rem_list:
        e_total = db.query(func.count(RemediationEffectRecord.id)).filter(
            RemediationEffectRecord.remediation_id == rem.id,
            RemediationEffectRecord.created_at >= since,
        ).scalar() or 0
        e_resolved = db.query(func.count(RemediationEffectRecord.id)).filter(
            RemediationEffectRecord.remediation_id == rem.id,
            RemediationEffectRecord.created_at >= since,
            RemediationEffectRecord.effect == "resolved",
        ).scalar() or 0
        rem_stats.append({
            "remediation_id": rem.id,
            "name": rem.name,
            "action_type": rem.action_type,
            "total": e_total,
            "resolved": e_resolved,
            "success_rate": round(e_resolved / max(e_total, 1) * 100, 1),
        })

    return {
        "total": total,
        "resolved": resolved,
        "improved": improved,
        "no_change": no_change,
        "worsened": worsened,
        "success_rate": success_rate,
        "improve_rate": improve_rate,
        "period_days": days,
        "by_remediation": rem_stats,
    }


def get_effect_history(db: Session, page: int = 1, per_page: int = 20):
    q = db.query(RemediationEffectRecord).order_by(RemediationEffectRecord.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return items, total


def get_remediation_recommendations(db: Session, limit: int = 5) -> list:
    rem_list = db.query(AutoRemediation).filter(AutoRemediation.enabled == True).all()
    results = []
    for rem in rem_list:
        total = db.query(func.count(RemediationEffectRecord.id)).filter(
            RemediationEffectRecord.remediation_id == rem.id,
        ).scalar() or 0
        if total < 3:
            continue
        resolved = db.query(func.count(RemediationEffectRecord.id)).filter(
            RemediationEffectRecord.remediation_id == rem.id,
            RemediationEffectRecord.effect == "resolved",
        ).scalar() or 0
        rate = resolved / max(total, 1)
        if rate >= 0.7:
            results.append({
                "remediation_id": rem.id,
                "name": rem.name,
                "action_type": rem.action_type,
                "total_executions": total,
                "resolved_count": resolved,
                "success_rate": round(rate * 100, 1),
                "recommendation": "高置信度推荐" if rate >= 0.8 else "可考虑使用",
            })
    results.sort(key=lambda x: x["success_rate"], reverse=True)
    return results[:limit]
