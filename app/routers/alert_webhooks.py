import json
import urllib.request
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AlertWebhook
from app.template_utils import get_templates

router = APIRouter(prefix="/alert-webhooks", tags=["alert_webhooks"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def list_webhooks(request: Request, db: Session = Depends(get_db)):
    hooks = db.query(AlertWebhook).order_by(AlertWebhook.id.desc()).all()
    return templates.TemplateResponse("alert_webhooks.html", {"request": request, "hooks": hooks})


@router.post("/create")
def create_webhook(
    name: str = Form(...),
    url: str = Form(...),
    secret: str = Form(""),
    retry_count: int = Form(3),
    timeout: int = Form(10),
    db: Session = Depends(get_db),
):
    hook = AlertWebhook(
        name=name, url=url, secret=secret,
        retry_count=retry_count, timeout=timeout, enabled=True,
    )
    db.add(hook)
    db.commit()
    return RedirectResponse("/alert-webhooks", status_code=303)


@router.post("/{hook_id}/toggle")
def toggle_webhook(hook_id: int, db: Session = Depends(get_db)):
    h = db.query(AlertWebhook).filter(AlertWebhook.id == hook_id).first()
    if h:
        h.enabled = not h.enabled
        db.commit()
    return RedirectResponse("/alert-webhooks", status_code=303)


@router.post("/{hook_id}/test")
def test_webhook(hook_id: int, db: Session = Depends(get_db)):
    h = db.query(AlertWebhook).filter(AlertWebhook.id == hook_id).first()
    if not h:
        return RedirectResponse("/alert-webhooks", status_code=303)
    try:
        payload = json.dumps({"event": "test", "message": "AIOPS webhook test"}).encode()
        req = urllib.request.Request(h.url, payload, {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=h.timeout)
    except Exception:
        pass
    return RedirectResponse("/alert-webhooks", status_code=303)


@router.post("/{hook_id}/delete")
def delete_webhook(hook_id: int, db: Session = Depends(get_db)):
    h = db.query(AlertWebhook).filter(AlertWebhook.id == hook_id).first()
    if h:
        db.delete(h)
        db.commit()
    return RedirectResponse("/alert-webhooks", status_code=303)


def call_alert_webhooks(db: Session, alert):
    hooks = db.query(AlertWebhook).filter(AlertWebhook.enabled == True).all()
    for h in hooks:
        payload = json.dumps({
            "event": "alert",
            "alert_id": alert.id,
            "metric_name": alert.metric_name,
            "severity": alert.severity,
            "status": alert.status,
            "actual_value": alert.actual_value,
            "threshold": alert.threshold,
            "message": alert.message,
            "created_at": str(alert.created_at),
        }).encode()
        for attempt in range(h.retry_count):
            try:
                req = urllib.request.Request(h.url, payload, {"Content-Type": "application/json"})
                if h.secret:
                    req.add_header("Authorization", f"Bearer {h.secret}")
                urllib.request.urlopen(req, timeout=h.timeout)
                break
            except Exception:
                pass
