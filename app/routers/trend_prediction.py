from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import MetricRecord, Asset
from app.template_utils import get_templates

router = APIRouter(prefix="/trend-prediction", tags=["trend-prediction"])
templates = get_templates()


def simple_linear_regression(x, y):
    n = len(x)
    sx = sum(x)
    sy = sum(y)
    sxx = sum(v * v for v in x)
    sxy = sum(x[i] * y[i] for i in range(n))
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx) if (n * sxx - sx * sx) != 0 else 0
    intercept = (sy - slope * sx) / n
    return slope, intercept


@router.get("", response_class=HTMLResponse)
def trend_page(request: Request, db: Session = Depends(get_db)):
    metrics = [r[0] for r in db.query(MetricRecord.name).distinct().all()]
    return templates.TemplateResponse("trend_prediction.html", {
        "request": request, "metrics": metrics, "result": None,
    })


@router.post("/predict", response_class=HTMLResponse)
def trend_predict(
    request: Request,
    metric_name: str = Form(...),
    asset_id: int = Form(0),
    hours: int = Form(24),
    forecast_steps: int = Form(12),
    db: Session = Depends(get_db),
):
    since = datetime.now() - timedelta(hours=hours)
    q = db.query(MetricRecord).filter(
        MetricRecord.name == metric_name, MetricRecord.timestamp >= since
    )
    if asset_id > 0:
        q = q.filter(MetricRecord.asset_id == asset_id)
    records = q.order_by(MetricRecord.timestamp).all()

    if len(records) < 5:
        metrics = [r[0] for r in db.query(MetricRecord.name).distinct().all()]
        return templates.TemplateResponse("trend_prediction.html", {
            "request": request, "metrics": metrics,
            "error": f"数据点不足 ({len(records)} < 5)",
        })

    # Linear regression on time
    values = [r.value for r in records]
    timestamps = [r.timestamp for r in records]
    x = list(range(len(values)))
    slope, intercept = simple_linear_regression(x, values)

    # Forecast
    forecast = []
    last_x = len(values)
    for i in range(1, forecast_steps + 1):
        pred = slope * (last_x + i) + intercept
        forecast.append({"step": i, "predicted_value": round(pred, 2)})

    # Fit quality
    preds = [slope * i + intercept for i in x]
    residuals = [values[i] - preds[i] for i in range(len(values))]
    mae = sum(abs(r) for r in residuals) / len(residuals)

    # Trend direction
    direction = "up" if slope > 0 else "down"

    metrics = [r[0] for r in db.query(MetricRecord.name).distinct().all()]
    return templates.TemplateResponse("trend_prediction.html", {
        "request": request, "metrics": metrics,
        "result": {
            "metric_name": metric_name,
            "data_points": len(records),
            "slope": round(slope, 4),
            "intercept": round(intercept, 2),
            "direction": direction,
            "mae": round(mae, 2),
            "forecast": forecast,
            "latest_value": round(values[-1], 2) if values else 0,
        },
    })
