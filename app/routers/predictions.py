from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.template_utils import get_templates
from app.services import prediction_service

router = APIRouter(prefix="/predictions", tags=["predictions"])
templates = get_templates()


@router.get("/capacity", response_class=HTMLResponse)
def capacity_prediction(
    request: Request,
    metric: str = "",
    threshold: float = Query(None),
    hours_back: int = 168,
    db: Session = Depends(get_db),
):
    metrics = prediction_service.get_predictable_metrics(db)
    result = None
    if metric:
        result = prediction_service.predict_capacity(db, metric, hours_back, threshold)
    return templates.TemplateResponse("capacity_prediction.html", {
        "request": request,
        "metrics": metrics,
        "selected_metric": metric,
        "threshold": threshold,
        "hours_back": hours_back,
        "result": result,
        "svg": prediction_service.generate_trend_svg(result) if result else "",
    })

