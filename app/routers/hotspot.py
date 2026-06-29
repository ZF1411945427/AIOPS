import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from collections import defaultdict
from app.database import get_db
from app.models import MetricRecord, Asset
from app.template_utils import get_templates

router = APIRouter(prefix="/hotspot", tags=["hotspot"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def hotspot_view(
    request: Request,
    metric: str = "cpu_usage",
    hours: int = 1,
    db: Session = Depends(get_db),
):
    now = datetime.now()
    since = now - timedelta(hours=hours)
    before = since - timedelta(hours=hours)

    current_records = (
        db.query(MetricRecord)
        .filter(MetricRecord.name == metric, MetricRecord.timestamp >= since)
        .all()
    )
    baseline_records = (
        db.query(MetricRecord)
        .filter(MetricRecord.name == metric, MetricRecord.timestamp >= before, MetricRecord.timestamp < since)
        .all()
    )

    def _dimension_breakdown(records):
        breakdown = defaultdict(list)
        for r in records:
            labels = json.loads(r.labels) if isinstance(r.labels, str) else r.labels or {}
            for k, v in labels.items():
                breakdown[f"{k}={v}"].append(r.value)
        return {k: sum(v) / len(v) for k, v in breakdown.items()}

    current_dims = _dimension_breakdown(current_records)
    baseline_dims = _dimension_breakdown(baseline_records)

    changes = []
    all_keys = set(current_dims.keys()) | set(baseline_dims.keys())
    for key in all_keys:
        cur = current_dims.get(key, 0)
        base = baseline_dims.get(key, 0)
        if base > 0:
            chg = ((cur - base) / base) * 100
        else:
            chg = 0 if cur == 0 else 100
        changes.append({"dimension": key, "current": round(cur, 2), "baseline": round(base, 2), "change": round(chg, 1)})

    changes.sort(key=lambda x: abs(x["change"]), reverse=True)

    # 从数据库查实际有哪些指标，不再硬编码
    top_metrics = [r[0] for r in db.query(MetricRecord.name).distinct().order_by(MetricRecord.name).all()]
    if not top_metrics:
        top_metrics = ["cpu_usage", "memory_usage", "disk_usage"]

    return templates.TemplateResponse("hotspot.html", {
        "request": request,
        "metric": metric,
        "hours": hours,
        "changes": changes[:30],
        "top_metrics": top_metrics,
    })
