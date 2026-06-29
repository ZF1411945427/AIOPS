from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Incident, IncidentAlert, Alert, Asset


def list_incidents(db: Session, status: str = ""):
    q = db.query(Incident)
    if status:
        q = q.filter(Incident.status == status)
    return q.order_by(Incident.created_at.desc()).all()


def get_incident_detail(db: Session, incident_id: int):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        return None
    alert_ids = [ia.alert_id for ia in db.query(IncidentAlert).filter(IncidentAlert.incident_id == incident_id).all()]
    alerts = db.query(Alert).filter(Alert.id.in_(alert_ids)).order_by(Alert.created_at.desc()).all() if alert_ids else []
    asset = db.query(Asset).filter(Asset.id == incident.asset_id).first() if incident.asset_id else None
    return {"incident": incident, "alerts": alerts, "asset": asset}


def resolve_incident(db: Session, incident_id: int):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        return None
    incident.status = "resolved"
    incident.resolved_at = datetime.now()
    db.commit()
    db.refresh(incident)
    return incident


INCIDENT_WINDOW = timedelta(minutes=15)


def correlate_alerts(db: Session):
    now = datetime.now()
    cutoff = now - INCIDENT_WINDOW

    unresolved_alerts = (
        db.query(Alert)
        .filter(Alert.status.in_(["triggered", "acknowledged"]), Alert.created_at > cutoff)
        .order_by(Alert.asset_id, Alert.created_at)
        .all()
    )

    assets = {}
    for alert in unresolved_alerts:
        aid = alert.asset_id or 0
        if aid not in assets:
            assets[aid] = []
        assets[aid].append(alert)

    for asset_id, alerts in assets.items():
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        sev = min((a.severity for a in alerts), key=lambda s: severity_order.get(s, 99))
        title = f"Asset #{asset_id} fault - {len(alerts)} alerts"

        existing = (
            db.query(Incident)
            .filter(
                Incident.asset_id == (asset_id if asset_id > 0 else None),
                Incident.status == "open",
                Incident.created_at > cutoff,
            )
            .first()
        )
        if existing:
            existing.title = title
            existing.severity = sev
            existing.alert_count = len(alerts)
            db.commit()
            incident = existing
        else:
            incident = Incident(
                title=title, severity=sev, status="open",
                asset_id=asset_id if asset_id > 0 else None,
                alert_count=len(alerts),
            )
            db.add(incident)
            db.commit()
            db.refresh(incident)

        for alert in alerts:
            link = db.query(IncidentAlert).filter(
                IncidentAlert.incident_id == incident.id,
                IncidentAlert.alert_id == alert.id,
            ).first()
            if not link:
                db.add(IncidentAlert(incident_id=incident.id, alert_id=alert.id))
        db.commit()

    open_incidents = db.query(Incident).filter(Incident.status == "open").all()
    for inc in open_incidents:
        active_alerts = (
            db.query(IncidentAlert)
            .filter(IncidentAlert.incident_id == inc.id)
            .count()
        )
        if active_alerts == 0:
            inc.status = "resolved"
            inc.resolved_at = now
    db.commit()



