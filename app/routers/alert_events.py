from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Alert, K8sEvent, AlertEventLink
from app.template_utils import get_templates

router = APIRouter(prefix="/alert-events", tags=["alert_events"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def alert_event_list(request: Request, db: Session = Depends(get_db)):
    links = (
        db.query(AlertEventLink)
        .order_by(AlertEventLink.created_at.desc())
        .limit(100)
        .all()
    )
    alert_ids = list(set(l.alert_id for l in links))
    event_ids = list(set(l.event_id for l in links))
    alerts = {a.id: a for a in db.query(Alert).filter(Alert.id.in_(alert_ids)).all()} if alert_ids else {}
    events = {e.id: e for e in db.query(K8sEvent).filter(K8sEvent.id.in_(event_ids)).all()} if event_ids else {}
    return templates.TemplateResponse("alert_events.html", {
        "request": request, "links": links, "alerts": alerts, "events": events,
    })


@router.get("/auto-link")
def auto_link(db: Session = Depends(get_db)):
    """Auto-link recent alerts to K8s events by asset matching."""
    recent = datetime.now() - timedelta(hours=2)
    alerts = db.query(Alert).filter(
        Alert.created_at >= recent,
        Alert.asset_id != None,
    ).all()
    events = db.query(K8sEvent).filter(
        K8sEvent.last_seen >= recent,
    ).all()

    count = 0
    for a in alerts:
        for e in events:
            name_match = e.name and a.metric_name and e.name.lower() in a.metric_name.lower()
            ns_match = e.namespace and a.asset_id and str(a.asset_id) in e.namespace
            if name_match or ns_match:
                existing = db.query(AlertEventLink).filter(
                    AlertEventLink.alert_id == a.id,
                    AlertEventLink.event_id == e.id,
                ).first()
                if not existing:
                    db.add(AlertEventLink(alert_id=a.id, event_id=e.id, relation="auto_linked"))
                    count += 1
    db.commit()
    return HTMLResponse(f"自动关联完成: 创建 {count} 条关联")
