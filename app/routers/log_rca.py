from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Alert, MetricRecord, Asset, AssetRelation
from app.template_utils import get_templates

router = APIRouter(prefix="/log-rca", tags=["log-rca"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def log_rca_page(request: Request, db: Session = Depends(get_db)):
    alerts = db.query(Alert).order_by(Alert.id.desc()).limit(50).all()
    return templates.TemplateResponse("log_rca.html", {
        "request": request, "alerts": alerts, "result": None,
    })


@router.post("/analyze", response_class=HTMLResponse)
def log_rca_analyze(
    request: Request, alert_id: int = Form(...),
    window_minutes: int = Form(30),
    db: Session = Depends(get_db),
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return templates.TemplateResponse("log_rca.html", {
            "request": request, "error": "Alert not found",
        })
    since = (alert.created_at or datetime.now()) - timedelta(minutes=window_minutes)
    until = (alert.created_at or datetime.now()) + timedelta(minutes=5)

    # Find asset that this alert is about
    source_asset = None
    if alert.asset_id:
        source_asset = db.query(Asset).filter(Asset.id == alert.asset_id).first()

    # Find all metrics in time window around the alert
    metrics_in_window = (
        db.query(MetricRecord)
        .filter(MetricRecord.timestamp.between(since, until))
        .order_by(MetricRecord.timestamp.desc())
        .limit(200)
        .all()
    )

    # Group metrics by name, compute anomaly scores
    metric_groups = defaultdict(list)
    for m in metrics_in_window:
        metric_groups[m.name].append(m.value)

    metric_scores = []
    for name, vals in metric_groups.items():
        if len(vals) < 3:
            continue
        avg = sum(vals) / len(vals)
        std = (sum((v - avg) ** 2 for v in vals) / len(vals)) ** 0.5 or 1
        latest = vals[-1]
        z = abs(latest - avg) / std
        metric_scores.append({"metric": name, "latest": round(latest, 2),
                               "avg": round(avg, 2), "z_score": round(z, 3)})
    metric_scores.sort(key=lambda x: -x["z_score"])

    # Find connected assets
    connected = []
    if source_asset:
        relations = db.query(AssetRelation).filter(
            (AssetRelation.parent_id == source_asset.id) |
            (AssetRelation.child_id == source_asset.id)
        ).all()
        for r in relations:
            other_id = r.child_id if r.parent_id == source_asset.id else r.parent_id
            other = db.query(Asset).filter(Asset.id == other_id).first()
            if other:
                connected.append({"asset": other, "relation": r.relation or "connected"})

    alerts_list = db.query(Alert).order_by(Alert.id.desc()).limit(50).all()
    return templates.TemplateResponse("log_rca.html", {
        "request": request, "alerts": alerts_list,
        "result": {
            "alert": alert,
            "source_asset": source_asset,
            "anomalous_metrics": metric_scores[:20],
            "connected_assets": connected,
        },
    })
