from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.template_utils import get_templates

from datetime import datetime

from app.database import get_db
from app.services import alert_service
from app.models import AlertSilence
from sqlalchemy.orm import Session

router = APIRouter(prefix="/alerts", tags=["alerts"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def alert_list(request: Request, status: str = "", severity: str = "", db: Session = Depends(get_db)):
    alerts = alert_service.list_alerts(db, status, severity)
    rules = alert_service.list_rules(db)
    stats = alert_service.get_alert_stats(db)
    return templates.TemplateResponse("alerts.html", {
        "request": request,
        "alerts": alerts,
        "rules": rules,
        "stats": stats,
        "status_filter": status,
        "severity_filter": severity,
    })


@router.post("/batch/acknowledge")
def batch_acknowledge(db: Session = Depends(get_db)):
    count = alert_service.batch_acknowledge(db)
    return RedirectResponse("/alerts", status_code=303)


@router.post("/batch/resolve")
def batch_resolve(db: Session = Depends(get_db)):
    count = alert_service.batch_resolve(db)
    return RedirectResponse("/alerts", status_code=303)


@router.post("/check")
def check_alerts(db: Session = Depends(get_db)):
    new_alerts = alert_service.check_rules(db)
    return {"new_alerts": len(new_alerts)}


@router.get("/rules", response_class=HTMLResponse)
def rule_list(request: Request, db: Session = Depends(get_db)):
    rules = alert_service.list_rules(db)
    now = datetime.now()
    silences = db.query(AlertSilence).filter(AlertSilence.until > now).all()
    silence_map = {s.rule_id: s for s in silences}
    return templates.TemplateResponse("rules.html", {
        "request": request, "rules": rules, "silence_map": silence_map, "now": now,
    })


@router.post("/rules/create")
def rule_create(
    name: str = Form(...),
    metric_name: str = Form(...),
    condition: str = Form(...),
    threshold: float = Form(...),
    severity: str = Form("warning"),
    db: Session = Depends(get_db),
):
    alert_service.create_rule(db, {
        "name": name, "metric_name": metric_name,
        "condition": condition, "threshold": threshold,
        "severity": severity, "enabled": True,
    })
    return RedirectResponse("/alerts/rules", status_code=303)


@router.post("/rules/{rule_id}/silence")
def rule_silence(rule_id: int, minutes: int = Form(30), reason: str = Form(""), db: Session = Depends(get_db)):
    alert_service.create_silence(db, rule_id, minutes, reason)
    return RedirectResponse("/alerts/rules", status_code=303)


@router.post("/rules/{rule_id}/toggle")
def rule_toggle(rule_id: int, db: Session = Depends(get_db)):
    rule = alert_service.get_rule(db, rule_id)
    if rule:
        alert_service.update_rule(db, rule_id, {"enabled": not rule.enabled})
    return RedirectResponse("/alerts/rules", status_code=303)


@router.post("/rules/{rule_id}/delete")
def rule_delete(rule_id: int, db: Session = Depends(get_db)):
    alert_service.delete_rule(db, rule_id)
    return RedirectResponse("/alerts/rules", status_code=303)


@router.post("/silences/{silence_id}/delete")
def silence_delete(silence_id: int, db: Session = Depends(get_db)):
    alert_service.delete_silence(db, silence_id)
    return RedirectResponse("/alerts/rules", status_code=303)


@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db)):
    alert_service.acknowledge_alert(db, alert_id)
    return RedirectResponse("/alerts", status_code=303)


@router.post("/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    alert_service.resolve_alert(db, alert_id)
    return RedirectResponse("/alerts", status_code=303)


@router.get("/{alert_id}", response_class=HTMLResponse)
def alert_detail(alert_id: int, request: Request, db: Session = Depends(get_db)):
    detail = alert_service.get_alert_detail(db, alert_id)
    if not detail:
        return RedirectResponse("/alerts", status_code=303)
    return templates.TemplateResponse("alert_detail.html", {
        "request": request, **detail,
    })



