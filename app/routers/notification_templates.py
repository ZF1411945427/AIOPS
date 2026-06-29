from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import NotificationTemplate
from app.template_utils import get_templates

router = APIRouter(prefix="/notification-templates", tags=["notification_templates"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def list_templates(request: Request, db: Session = Depends(get_db)):
    templates_list = db.query(NotificationTemplate).order_by(NotificationTemplate.id.desc()).all()
    return templates.TemplateResponse("notification_templates.html", {
        "request": request, "templates": templates_list,
    })


@router.get("/new", response_class=HTMLResponse)
def new_template(request: Request):
    return templates.TemplateResponse("notification_template_form.html", {
        "request": request, "t": None,
    })


@router.post("/new")
def create_template(
    request: Request,
    name: str = Form(...),
    channel_type: str = Form(""),
    title_template: str = Form(""),
    body_template: str = Form(""),
    severity: str = Form("warning"),
    db: Session = Depends(get_db),
):
    t = NotificationTemplate(
        name=name,
        channel_type=channel_type,
        title_template=title_template or "{{ alert.severity }}: {{ alert.metric_name }}",
        body_template=body_template or "告警: {{ alert.message }}",
        severity=severity,
        enabled=True,
    )
    db.add(t)
    db.commit()
    return RedirectResponse("/notification-templates", status_code=303)


@router.post("/{t_id}/delete")
def delete_template(t_id: int, db: Session = Depends(get_db)):
    t = db.query(NotificationTemplate).filter(NotificationTemplate.id == t_id).first()
    if t:
        db.delete(t)
        db.commit()
    return RedirectResponse("/notification-templates", status_code=303)
