import json
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import SavedFilter, Alert, AlertRule, AlertEventLink, K8sEvent
from app.template_utils import get_templates

router = APIRouter(prefix="/alert-console", tags=["alert_console"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def alert_console(request: Request, db: Session = Depends(get_db)):
    alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(200).all()
    rules = {r.id: r for r in db.query(AlertRule).all()}
    saved_filters = db.query(SavedFilter).filter(SavedFilter.page == "alerts").all()
    event_links = {l.alert_id: l for l in db.query(AlertEventLink).all()}
    event_ids = list(set(l.event_id for l in event_links.values()))
    events = {e.id: e for e in db.query(K8sEvent).filter(K8sEvent.id.in_(event_ids)).all()} if event_ids else {}
    return templates.TemplateResponse("alert_console.html", {
        "request": request, "alerts": alerts, "rules": rules,
        "saved_filters": saved_filters,
        "event_links": event_links, "events": events,
    })


@router.post("/batch/acknowledge")
def batch_ack(ids: str = Form(""), db: Session = Depends(get_db)):
    for sid in ids.split(","):
        sid = sid.strip()
        if sid.isdigit():
            a = db.query(Alert).filter(Alert.id == int(sid)).first()
            if a and a.status == "triggered":
                a.status = "acknowledged"
    db.commit()
    return RedirectResponse("/alert-console", status_code=303)


@router.post("/batch/resolve")
def batch_resolve(ids: str = Form(""), db: Session = Depends(get_db)):
    for sid in ids.split(","):
        sid = sid.strip()
        if sid.isdigit():
            a = db.query(Alert).filter(Alert.id == int(sid)).first()
            if a and a.status in ("triggered", "acknowledged"):
                a.status = "resolved"
    db.commit()
    return RedirectResponse("/alert-console", status_code=303)


@router.post("/filters/save")
def save_filter(
    request: Request,
    name: str = Form(...),
    filters: str = Form("{}"),
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")
    db.add(SavedFilter(name=name, page="alerts", filters=filters, user_id=user_id))
    db.commit()
    return RedirectResponse("/alert-console", status_code=303)


@router.post("/filters/{fid}/delete")
def delete_filter(fid: int, db: Session = Depends(get_db)):
    db.query(SavedFilter).filter(SavedFilter.id == fid).delete()
    db.commit()
    return RedirectResponse("/alert-console", status_code=303)
