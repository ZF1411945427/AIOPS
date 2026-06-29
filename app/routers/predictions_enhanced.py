import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
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


@router.get("/life", response_class=HTMLResponse)
def remaining_life(request: Request, asset_id: int = 0, metric: str = "disk_usage", db: Session = Depends(get_db)):
    assets = db.query(Asset).filter(Asset.ci_type.in_(["server", "node"])).order_by(Asset.name).all()
    prediction = None
    selected_asset = None
    if asset_id:
        selected_asset = db.query(Asset).filter(Asset.id == asset_id).first()
        since = datetime.now() - timedelta(days=7)
        records = (
            db.query(MetricRecord)
            .filter(MetricRecord.name == metric, MetricRecord.timestamp >= since)
            .order_by(MetricRecord.timestamp.asc())
            .all()
        )
        if records and len(records) >= 2:
            slope, intercept = _linear_degradation(records, records[-1].value)
            if slope and slope > 0:
                current = records[-1].value
                threshold = 95.0
                remaining_hours = (threshold - current) / slope if slope > 0 else None
                if remaining_hours and remaining_hours > 0:
                    prediction = {
                        "current": round(current, 1),
                        "slope": round(slope, 4),
                        "threshold": threshold,
                        "remaining_hours": round(remaining_hours, 1),
                        "remaining_days": round(remaining_hours / 24, 1),
                        "estimated_failure": (datetime.now() + timedelta(hours=remaining_hours)).strftime("%Y-%m-%d"),
                    }
    return templates.TemplateResponse("predictions_life.html", {
        "request": request, "assets": assets, "selected_asset": selected_asset,
        "metric": metric, "prediction": prediction,
    })


@router.get("/failure", response_class=HTMLResponse)
def failure_prob(request: Request, asset_id: int = 0, hours: int = 24, db: Session = Depends(get_db)):
    assets = db.query(Asset).order_by(Asset.name).all()
    results = []
    if asset_id:
        target = db.query(Asset).filter(Asset.id == asset_id).first()
        if target:
            for m in ["cpu_usage", "memory_usage", "disk_usage"]:
                latest = db.query(MetricRecord).filter(MetricRecord.name == m).order_by(MetricRecord.timestamp.desc()).first()
                if latest:
                    prob = _failure_probability(latest.value, 90.0 if m == "cpu_usage" else 95.0, "warning")
                    results.append({"metric": m, "value": round(latest.value, 1), "probability": round(prob, 1)})
    else:
        asset_ids = [r[0] for r in db.query(Alert.asset_id).filter(Alert.status == "triggered").distinct().limit(10).all() if r[0]]
        for aid in asset_ids:
            asset = db.query(Asset).filter(Asset.id == aid).first()
            if asset:
                probs = []
                for m in ["cpu_usage", "memory_usage", "disk_usage"]:
                    latest = db.query(MetricRecord).filter(MetricRecord.name == m).order_by(MetricRecord.timestamp.desc()).first()
                    if latest:
                        probs.append(_failure_probability(latest.value, 90.0, "warning"))
                avg_prob = sum(probs) / len(probs) if probs else 0
                results.append({"asset": asset, "average_probability": round(avg_prob, 1), "details": probs})
    return templates.TemplateResponse("predictions_failure.html", {
        "request": request, "assets": assets, "asset_id": asset_id,
        "results": results, "hours": hours,
    })
