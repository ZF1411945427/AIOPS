from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.template_utils import get_templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def notification_page(request: Request, db: Session = Depends(get_db)):
    channels = notification_service.get_channels(db)
    logs = notification_service.get_notification_logs(db)
    return templates.TemplateResponse("notifications.html", {
        "request": request,
        "channels": channels,
        "logs": logs,
    })


@router.post("/channels/create")
def create_channel(
    name: str = Form(...),
    type: str = Form(...),
    config_host: str = Form(""),
    config_port: int = Form(587),
    config_user: str = Form(""),
    config_password: str = Form(""),
    config_recipients: str = Form(""),
    config_url: str = Form(""),
    config_webhook: str = Form(""),
    db: Session = Depends(get_db),
):
    config = {}
    if type == "email":
        config = {
            "host": config_host, "port": config_port,
            "user": config_user, "password": config_password,
            "recipients": config_recipients,
        }
    elif type == "webhook":
        config = {"url": config_url}
    elif type == "dingtalk":
        config = {"webhook": config_webhook}
    elif type == "wecom":
        config = {"webhook": config_webhook}
    notification_service.create_channel(db, {"name": name, "type": type, "config": config, "enabled": True})
    return RedirectResponse("/notifications", status_code=303)


@router.post("/channels/{channel_id}/delete")
def delete_channel(channel_id: int, db: Session = Depends(get_db)):
    notification_service.delete_channel(db, channel_id)
    return RedirectResponse("/notifications", status_code=303)


