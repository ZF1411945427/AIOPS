from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import Alert, Asset, Incident


def compute_health_score(db: Session, target_asset_id: Optional[int] = None) -> dict:
    total_assets = db.query(func.count(Asset.id)).scalar() or 1
    online_assets = db.query(func.count(Asset.id)).filter(Asset.status == "online").scalar() or 0
    triggered_alerts = db.query(func.count(Alert.id)).filter(Alert.status == "triggered").scalar() or 0
    acknowledged_alerts = db.query(func.count(Alert.id)).filter(Alert.status == "acknowledged").scalar() or 0
    open_incidents = db.query(func.count(Incident.id)).filter(Incident.status == "open").scalar() or 0

    asset_score = (online_assets / total_assets) * 40
    alert_penalty = min(triggered_alerts * 5, 30)
    incident_penalty = min(open_incidents * 10, 20)
    ack_bonus = min(acknowledged_alerts * 1, 10)

    score = max(0, min(100, asset_score - alert_penalty - incident_penalty + ack_bonus))

    status = "healthy"
    if score < 60:
        status = "danger"
    elif score < 80:
        status = "warning"

    return {
        "score": round(score, 1),
        "status": status,
        "asset_score": round(asset_score, 1),
        "alert_penalty": alert_penalty,
        "incident_penalty": incident_penalty,
        "ack_bonus": ack_bonus,
        "triggered_alerts": triggered_alerts,
        "open_incidents": open_incidents,
        "total_assets": total_assets,
        "online_assets": online_assets,
    }
