from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from app.database import get_db
from app.models import Asset, Alert, AlertRule, Incident, DataSource, MetricRecord
from app.services.health_score_service import compute_health_score
from app.services.metric_v2_service import query_range_data, query_latest_values, query_metric_names, is_vm_available
from app.template_utils import get_templates
from app.cache import cached

router = APIRouter(tags=["dashboard"])
templates = get_templates()

_TIME_RANGE_MAP = {
    "1h": 1, "6h": 6, "24h": 24,
    "7d": 168, "30d": 720,
}

def _parse_time_range(time_range: str) -> int:
    return _TIME_RANGE_MAP.get(time_range, 24)

def _query_vm_metric(asset_id: int, metric_name: str, hours: int) -> list:
    try:
        if asset_id and asset_id > 0:
            query = f'{metric_name}{{asset_id="{asset_id}"}}'
        else:
            query = f'{{__name__=~"{metric_name}"}}'
        now_s = int(datetime.now().timestamp())
        start_s = now_s - hours * 3600
        from app.services.metric_v2_service import query_promql_range
        result = query_promql_range(query, start_s, now_s, step="60s" if hours <= 6 else "300s")
        if result.get("status") != "success":
            return []
        points = []
        for item in result.get("data", {}).get("result", []):
            metric = item.get("metric", {})
            for ts, val in item.get("values", []):
                points.append({
                    "time": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                    "value": round(float(val), 2),
                    "asset_id": int(metric.get("asset_id", 0)) or asset_id,
                })
        points.sort(key=lambda x: x["time"])
        return points
    except Exception:
        return []


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
def dashboard_data(
    db: Session = Depends(get_db),
    time_range: str = Query("24h", description="时间范围: 1h/6h/24h/7d/30d"),
    asset_id: int = Query(0, description="资产ID，0=全部"),
):
    hours = _parse_time_range(time_range)
    now = datetime.utcnow()

    # Stats
    asset_total = db.query(func.count(Asset.id)).scalar() or 0
    asset_online = db.query(func.count(Asset.id)).filter(Asset.status == "online").scalar() or 0
    alert_active = db.query(func.count(Alert.id)).filter(Alert.status.in_(["firing", "triggered"])).scalar() or 0
    rule_count = db.query(func.count(AlertRule.id)).scalar() or 0
    incident_open = db.query(func.count(Incident.id)).filter(Incident.status == "open").scalar() or 0
    datasource_count = db.query(func.count(DataSource.id)).scalar() or 0
    health = compute_health_score(db, target_asset_id=asset_id if asset_id > 0 else None)

    # Asset type distribution
    asset_types = db.query(Asset.ci_type, func.count(Asset.id).label("count")).group_by(Asset.ci_type).order_by(text("count desc")).all()
    asset_type_dist = [{"type": t, "count": c} for t, c in asset_types]

    # Alert severity distribution (filtered by time_range + asset_id)
    alert_filter = db.query(Alert)
    cutoff = now - timedelta(hours=hours)
    alert_filter = alert_filter.filter(Alert.created_at >= cutoff)
    if asset_id > 0:
        alert_filter = alert_filter.filter(Alert.asset_id == asset_id)
    sev_dist = alert_filter.with_entities(Alert.severity, func.count(Alert.id).label("count")).group_by(Alert.severity).all()
    severity_dist = [{"severity": s, "count": c} for s, c in sev_dist]

    # Alert trend (by day/hour)
    if hours <= 24:
        fmt = "%Y-%m-%d %H:00"
        group_expr = func.strftime("%Y-%m-%d %H:00", Alert.created_at)
    else:
        fmt = "%Y-%m-%d"
        group_expr = func.strftime("%Y-%m-%d", Alert.created_at)
    alert_rows = alert_filter.with_entities(
        group_expr.label("period"),
        func.count(Alert.id).label("count")
    ).group_by("period").order_by("period").all()
    alert_trend = [{"date": r.period, "count": r.count} for r in alert_rows]

    # Recent alerts
    recent = db.query(Alert, Asset.name.label("asset_name")).outerjoin(
        Asset, Alert.asset_id == Asset.id
    ).order_by(Alert.created_at.desc()).limit(10).all()
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

    # VM metric trends (CPU, memory, disk, network for the selected asset)
    vm_available = is_vm_available()
    vm_metrics = {}
    if vm_available:
        vm_metric_names = ["cpu_usage", "memory_usage", "disk_usage", "network_rx_bytes", "network_tx_bytes", "loadavg_1min"]
        for vm_name in vm_metric_names:
            data_points = _query_vm_metric(asset_id, vm_name, hours)
            if data_points:
                vm_metrics[vm_name] = data_points

    # Asset list for filter dropdown
    assets_list = db.query(Asset.id, Asset.name, Asset.ip).order_by(Asset.name).all()
    assets_for_select = [{"id": a.id, "name": a.name, "ip": a.ip} for a in assets_list]

    # Online count by ci_type
    online_by_type = db.query(Asset.ci_type, func.count(Asset.id).label("count")).filter(
        Asset.status == "online"
    ).group_by(Asset.ci_type).all()
    online_by_type_data = [{"type": t, "count": c} for t, c in online_by_type]

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
        "vm_metrics": vm_metrics,
        "vm_available": vm_available,
        "assets": assets_for_select,
        "online_by_type": online_by_type_data,
        "time_range": time_range,
        "asset_id": asset_id,
    })


