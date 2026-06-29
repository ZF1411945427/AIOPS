from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AlertSuppression, SystemConfig, AlertRule
from app.services import alert_service
from app.template_utils import get_templates

router = APIRouter(prefix="/alert-storm", tags=["alert_storm"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def storm_page(request: Request, db: Session = Depends(get_db)):
    stats = alert_service.get_alert_stats(db)
    suppressions = db.query(AlertSuppression).order_by(AlertSuppression.created_at.desc()).limit(100).all()
    configs = {c.key: c for c in db.query(SystemConfig).all()}
    storm_threshold = configs.get("storm_threshold").value if configs.get("storm_threshold") else "3"
    return templates.TemplateResponse("alert_storm.html", {
        "request": request, "stats": stats,
        "suppressions": suppressions,
        "storm_threshold": storm_threshold,
    })


@router.post("/config")
def storm_config(storm_threshold: int = Form(3), db: Session = Depends(get_db)):
    cfg = db.query(SystemConfig).filter(SystemConfig.key == "storm_threshold").first()
    if cfg:
        cfg.value = str(storm_threshold)
    else:
        db.add(SystemConfig(key="storm_threshold", value=str(storm_threshold), description="风暴阈值"))
    db.commit()
    return RedirectResponse("/alert-storm", status_code=303)
