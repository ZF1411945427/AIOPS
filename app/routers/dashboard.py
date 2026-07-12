from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from app.database import get_db
from app.models import Asset, Alert, AlertRule, Incident, DataSource, MetricRecord
from app.services.health_score_service import compute_health_score
from app.template_utils import get_templates
from app.cache import cached

router = APIRouter(tags=["dashboard"])
templates = get_templates()

@router.get("/api/dashboard/stats")
@cached(ttl=15)
def dashboard_stats(db: Session = Depends(get_db)):
    asset_total = db.query(func.count(Asset.id)).scalar() or 0
    asset_online = db.query(func.count(Asset.id)).filter(Asset.status == "online").scalar() or 0
    alert_active = db.query(func.count(Alert.id)).filter(Alert.status.in_(["firing", "triggered"])).scalar() or 0
    rule_count = db.query(func.count(AlertRule.id)).scalar() or 0
    return JSONResponse({
        "asset_total": asset_total,
        "asset_online": asset_online,
        "alert_active": alert_active,
        "rule_count": rule_count,
    })


@router.get("/api/dashboard/data")
@cached(ttl=15)
def dashboard_data(db: Session = Depends(get_db)):
    # Stats
    asset_total = db.query(func.count(Asset.id)).scalar() or 0
    asset_online = db.query(func.count(Asset.id)).filter(Asset.status == "online").scalar() or 0
    alert_active = db.query(func.count(Alert.id)).filter(Alert.status.in_(["firing", "triggered"])).scalar() or 0
    rule_count = db.query(func.count(AlertRule.id)).scalar() or 0
    incident_open = db.query(func.count(Incident.id)).filter(Incident.status == "open").scalar() or 0
    datasource_count = db.query(func.count(DataSource.id)).scalar() or 0
    health = compute_health_score(db)

    # Asset type distribution
    asset_types = db.query(Asset.type, func.count(Asset.id).label("count")).group_by(Asset.type).order_by(text("count desc")).all()
    asset_type_dist = [{"type": t, "count": c} for t, c in asset_types]

    # Alert severity distribution
    sev_dist = db.query(Alert.severity, func.count(Alert.id).label("count")).group_by(Alert.severity).all()
    severity_dist = [{"severity": s, "count": c} for s, c in sev_dist]

    # Alert trend (last 7 days, by day)
    seven_days = datetime.utcnow() - timedelta(days=7)
    alert_rows = db.query(
        func.strftime("%Y-%m-%d", Alert.created_at).label("day"),
        func.count(Alert.id).label("count")).filter(Alert.created_at >= seven_days).group_by("day").order_by("day").all()
    alert_trend = [{"date": r.day, "count": r.count} for r in alert_rows]

    # Recent alerts
    recent = db.query(Alert, Asset.name.label("asset_name")).outerjoin(Asset, Alert.asset_id == Asset.id).order_by(Alert.created_at.desc()).limit(10).all()
    recent_alerts = []
    for alert, asset_name in recent:
        recent_alerts.append({
            "id": alert.id,
            "metric_name": alert.metric_name,
            "severity": alert.severity,
            "status": alert.status,
            "asset_name": asset_name or "-",
            "message": alert.message,
            "created_at": alert.created_at.isoformat() if alert.created_at else "",
        })

    # Incident by status
    inc_status = db.query(Incident.status, func.count(Incident.id).label("count")).group_by(Incident.status).all()
    incident_status = [{"status": s, "count": c} for s, c in inc_status]

    return JSONResponse({
        "stats": {
            "asset_total": asset_total,
            "asset_online": asset_online,
            "alert_active": alert_active,
            "rule_count": rule_count,
            "incident_open": incident_open,
            "datasource_count": datasource_count,
            "health_score": health["score"],
            "health_status": health["status"],
        },
        "asset_type_distribution": asset_type_dist,
        "severity_distribution": severity_dist,
        "alert_trend": alert_trend,
        "incident_status": incident_status,
        "recent_alerts": recent_alerts,
    })


