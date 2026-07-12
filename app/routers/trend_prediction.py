from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
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


@router.get("/status")
def status():
    return {"module": "trend_prediction", "status": "ok"}


@router.get("/predict")
def predict(asset_id: int, metric_name: str, hours: int = 168, db: Session = Depends(get_db)):
    since = datetime.now() - timedelta(hours=hours)
    records = (
        db.query(MetricRecord)
        .filter(MetricRecord.asset_id == asset_id, MetricRecord.metric_name == metric_name, MetricRecord.timestamp >= since)
        .order_by(MetricRecord.timestamp)
        .all()
    )
    if len(records) < 2:
        return {"prediction": None, "reason": "insufficient data"}
    x = [i for i in range(len(records))]
    y = [r.value for r in records]
    slope, intercept = simple_linear_regression(x, y)
    next_x = len(records)
    predicted_next = slope * next_x + intercept
    return {
        "slope": slope,
        "intercept": intercept,
        "predicted_next": predicted_next,
        "n": len(records),
    }


