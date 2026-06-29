import math
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
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


@router.get("", response_class=HTMLResponse)
def correlation_view(
    request: Request,
    hours: int = 24,
    db: Session = Depends(get_db),
):
    since = datetime.now() - timedelta(hours=hours)
    records = db.query(MetricRecord).filter(MetricRecord.timestamp >= since).order_by(MetricRecord.timestamp).all()

    series = defaultdict(list)
    timestamps = defaultdict(list)
    for r in records:
        series[r.name].append(r.value)
        timestamps[r.name].append(r.timestamp)

    metrics = sorted(series.keys())
    matrix = []
    for m1 in metrics:
        row = {"name": m1}
        correlations = {}
        for m2 in metrics:
            if m1 == m2:
                correlations[m2] = 1.0
            else:
                pairs = list(zip(series[m1], series[m2]))
                if len(pairs) >= 3:
                    xs, ys = zip(*pairs)
                    correlations[m2] = round(_pearson(list(xs), list(ys)), 4)
                else:
                    correlations[m2] = 0
        row["correlations"] = correlations
        matrix.append(row)

    top_pairs = []
    for i, m1 in enumerate(metrics):
        for m2 in metrics[i + 1:]:
            pairs = list(zip(series[m1], series[m2]))
            if len(pairs) >= 3:
                xs, ys = zip(*pairs)
                r_val = _pearson(list(xs), list(ys))
                top_pairs.append({
                    "m1": m1,
                    "m2": m2,
                    "r": round(r_val, 4),
                    "abs_r": abs(r_val),
                })
    top_pairs.sort(key=lambda x: x["abs_r"], reverse=True)
    top_pairs = top_pairs[:20]

    return templates.TemplateResponse("correlation.html", {
        "request": request,
        "metrics": metrics,
        "matrix": matrix,
        "top_pairs": top_pairs,
        "hours": hours,
    })
