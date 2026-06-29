from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.template_utils import get_templates

from app.database import get_db
from app.services import anomaly_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/anomaly", tags=["anomaly"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def anomaly_page(request: Request, db: Session = Depends(get_db)):
    configs = anomaly_service.list_configs(db)
    return templates.TemplateResponse("anomaly.html", {
        "request": request, "configs": configs,
    })


@router.post("/configs/create")
def config_create(
    name: str = Form(...),
    metric_name: str = Form(...),
    asset_id: int = Form(0),
    algorithm: str = Form("sigma"),
    sensitivity: float = Form(3.0),
    window_size: int = Form(20),
    period: int = Form(12),
    db: Session = Depends(get_db),
):
    anomaly_service.create_config(db, {
        "name": name, "metric_name": metric_name,
        "asset_id": asset_id if asset_id > 0 else None,
        "algorithm": algorithm,
        "sensitivity": sensitivity, "window_size": window_size,
        "period": period,
        "enabled": True,
    })
    return RedirectResponse("/anomaly", status_code=303)


@router.post("/configs/{config_id}/toggle")
def config_toggle(config_id: int, db: Session = Depends(get_db)):
    anomaly_service.toggle_config(db, config_id)
    return RedirectResponse("/anomaly", status_code=303)


@router.post("/configs/{config_id}/delete")
def config_delete(config_id: int, db: Session = Depends(get_db)):
    anomaly_service.delete_config(db, config_id)
    return RedirectResponse("/anomaly", status_code=303)


