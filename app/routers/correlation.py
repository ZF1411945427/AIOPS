import math
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.template_utils import get_templates
from app.models import MetricRecord

router = APIRouter(prefix="/correlation", tags=["correlation"])
templates = get_templates()


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(a * b for a, b in zip(xs, ys))
    sum_xx = sum(a * a for a in xs)
    sum_yy = sum(b * b for b in ys)
    denom = math.sqrt((n * sum_xx - sum_x * sum_x) * (n * sum_yy - sum_y * sum_y))
    if denom == 0:
        return 0
    return (n * sum_xy - sum_x * sum_y) / denom


@router.get("/status")
def status():
    return {"module": "correlation", "status": "ok"}


@router.get("/correlate")
def correlate(asset_id: int, metric1: str, metric2: str, hours: int = 24, db: Session = Depends(get_db)):
    since = datetime.now() - timedelta(hours=hours)
    recs1 = (
        db.query(MetricRecord)
        .filter(MetricRecord.asset_id == asset_id, MetricRecord.metric_name == metric1, MetricRecord.timestamp >= since)
        .order_by(MetricRecord.timestamp)
        .all()
    )
    recs2 = (
        db.query(MetricRecord)
        .filter(MetricRecord.asset_id == asset_id, MetricRecord.metric_name == metric2, MetricRecord.timestamp >= since)
        .order_by(MetricRecord.timestamp)
        .all()
    )
    xs = [r.value for r in recs1]
    ys = [r.value for r in recs2]
    n = min(len(xs), len(ys))
    if n == 0:
        return {"correlation": 0, "n": 0, "metric1": metric1, "metric2": metric2}
    coef = _pearson(xs[:n], ys[:n])
    return {"correlation": coef, "n": n, "metric1": metric1, "metric2": metric2}


