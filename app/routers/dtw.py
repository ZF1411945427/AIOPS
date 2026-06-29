from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import MetricRecord, Asset
from app.services.dtw_service import find_similar_metrics
from app.template_utils import get_templates

router = APIRouter(prefix="/dtw", tags=["dtw"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def dtw_page(request: Request, db: Session = Depends(get_db)):
    metric_names = [r[0] for r in db.query(MetricRecord.name).distinct().all()]
    assets = db.query(Asset).order_by(Asset.name).all()
    return templates.TemplateResponse("dtw.html", {
        "request": request, "metric_names": metric_names, "assets": assets,
        "result": None,
    })


@router.post("/search", response_class=HTMLResponse)
def dtw_search(
    request: Request,
    metric_name: str = Form(...),
    asset_id: int = Form(0),
    hours: int = Form(6),
    top_k: int = Form(10),
    db: Session = Depends(get_db),
):
    result = find_similar_metrics(db, metric_name, asset_id=asset_id or None,
                                   hours=hours, top_k=top_k)
    metric_names = [r[0] for r in db.query(MetricRecord.name).distinct().all()]
    assets = db.query(Asset).order_by(Asset.name).all()
    return templates.TemplateResponse("dtw.html", {
        "request": request, "metric_names": metric_names, "assets": assets,
        "result": result, "query_metric": metric_name,
    })
