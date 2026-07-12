import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import MetricRecord, Asset, Alert, PredictionModel
from app.template_utils import get_templates

router = APIRouter(prefix="/predictions-enhanced", tags=["predictions_enhanced"])
templates = get_templates()


def _linear_degradation(records, current_value):
    if len(records) < 2:
        return None, None
    times = [(r.timestamp.timestamp() - records[0].timestamp.timestamp()) / 3600 for r in records]
    values = [r.value for r in records]
    n = len(times)
    slope = (n * sum(t * v for t, v in zip(times, values)) - sum(times) * sum(values)) / (n * sum(t * t for t in times) - sum(times) ** 2) if (n * sum(t * t for t in times) - sum(times) ** 2) != 0 else 0
    intercept = (sum(values) - slope * sum(times)) / n
    return slope, intercept


def _failure_probability(metric_value, threshold, severity):
    if severity == "critical":
        ratio = metric_value / threshold if threshold > 0 else 1
    else:
        ratio = metric_value / (threshold * 0.85) if threshold > 0 else 1
    return min(100, max(0, (ratio - 0.6) / 0.4 * 100))


@router.get("/status")
def status():
    return {"module": "predictions_enhanced", "status": "ok"}


@router.get("/predict")
def predict(asset_id: int, metric_name: str, threshold: float = 100, severity: str = "warning", hours: int = 168, db: Session = Depends(get_db)):
    since = datetime.now() - timedelta(hours=hours)
    records = (
        db.query(MetricRecord)
        .filter(MetricRecord.asset_id == asset_id, MetricRecord.metric_name == metric_name, MetricRecord.timestamp >= since)
        .order_by(MetricRecord.timestamp)
        .all()
    )
    if len(records) < 2:
        return {"prediction": None, "reason": "insufficient data"}
    current_value = records[-1].value
    slope, intercept = _linear_degradation(records, current_value)
    prob = _failure_probability(current_value, threshold, severity)
    return {
        "slope": slope,
        "intercept": intercept,
        "current_value": current_value,
        "failure_probability": prob,
        "threshold": threshold,
        "severity": severity,
        "n": len(records),
    }


