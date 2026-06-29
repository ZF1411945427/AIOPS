import json
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ReportSchedule
from app.template_utils import get_templates

router = APIRouter(prefix="/report-schedules", tags=["report_schedules"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def schedule_list(request: Request, db: Session = Depends(get_db)):
    schedules = db.query(ReportSchedule).order_by(ReportSchedule.created_at.desc()).all()
    return templates.TemplateResponse("report_schedules.html", {
        "request": request, "schedules": schedules,
    })


@router.post("/new")
def schedule_new(
    name: str = Form(...),
    report_type: str = Form("daily"),
    cron_expr: str = Form("0 8 * * *"),
    channel: str = Form("email"),
    channel_config: str = Form("{}"),
    db: Session = Depends(get_db),
):
    db.add(ReportSchedule(
        name=name, report_type=report_type, cron_expr=cron_expr,
        channel=channel, channel_config=channel_config,
    ))
    db.commit()
    return RedirectResponse("/report-schedules", status_code=303)


@router.post("/{sid}/toggle")
def schedule_toggle(sid: int, db: Session = Depends(get_db)):
    s = db.query(ReportSchedule).filter(ReportSchedule.id == sid).first()
    if s:
        s.enabled = not s.enabled
        db.commit()
    return RedirectResponse("/report-schedules", status_code=303)


@router.post("/{sid}/delete")
def schedule_delete(sid: int, db: Session = Depends(get_db)):
    db.query(ReportSchedule).filter(ReportSchedule.id == sid).delete()
    db.commit()
    return RedirectResponse("/report-schedules", status_code=303)
