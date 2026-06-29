from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AlertSilenceSchedule
from app.template_utils import get_templates

router = APIRouter(prefix="/alert-silence", tags=["alert_silence"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def list_schedules(request: Request, db: Session = Depends(get_db)):
    schedules = db.query(AlertSilenceSchedule).order_by(AlertSilenceSchedule.id.desc()).all()
    return templates.TemplateResponse("alert_silence_schedules.html", {
        "request": request, "schedules": schedules,
    })


@router.get("/new", response_class=HTMLResponse)
def new_schedule(request: Request):
    return templates.TemplateResponse("alert_silence_form.html", {
        "request": request, "s": None,
    })


@router.post("/new")
def create_schedule(request: Request, db: Session = Depends(get_db)):
    form = request.form()
    s = AlertSilenceSchedule(
        rule_id=int(form["rule_id"]) if form.get("rule_id") else None,
        metric_name=form.get("metric_name", ""),
        asset_id=int(form["asset_id"]) if form.get("asset_id") else None,
        cron_expr=form.get("cron_expr", "0 2 * * 0"),
        duration_minutes=int(form.get("duration_minutes", 120)),
        reason=form.get("reason", ""),
        enabled=True,
    )
    db.add(s)
    db.commit()
    return RedirectResponse("/alert-silence", status_code=303)


@router.post("/{s_id}/toggle")
def toggle_schedule(s_id: int, db: Session = Depends(get_db)):
    s = db.query(AlertSilenceSchedule).filter(AlertSilenceSchedule.id == s_id).first()
    if s:
        s.enabled = not s.enabled
        db.commit()
    return RedirectResponse("/alert-silence", status_code=303)


@router.post("/{s_id}/delete")
def delete_schedule(s_id: int, db: Session = Depends(get_db)):
    s = db.query(AlertSilenceSchedule).filter(AlertSilenceSchedule.id == s_id).first()
    if s:
        db.delete(s)
        db.commit()
    return RedirectResponse("/alert-silence", status_code=303)
