from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.template_utils import get_templates

from app.database import get_db
from app.services import config_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/settings", tags=["settings"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    configs = config_service.get_all_configs(db)
    return templates.TemplateResponse("settings.html", {
        "request": request, "configs": configs,
    })


@router.post("/update")
def settings_update(
    background_interval: str = Form("10"),
    data_retention_days: str = Form("30"),
    alert_retention_days: str = Form("90"),
    escalation_minutes: str = Form("5"),
    dedup_window_minutes: str = Form("5"),
    storm_threshold: str = Form("3"),
    incident_window_minutes: str = Form("15"),
    smtp_host: str = Form(""),
    smtp_port: str = Form("587"),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
    smtp_recipients: str = Form(""),
    asset_probe_enabled: str = Form("true"),
    asset_probe_interval: str = Form("60"),
    asset_probe_timeout: str = Form("10"),
    db: Session = Depends(get_db),
):
    updates = {k: v for k, v in locals().items() if k != "db"}
    config_service.update_configs(db, updates)
    return RedirectResponse("/settings", status_code=303)


