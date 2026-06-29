import itertools
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import MetricRecord, Asset
from app.template_utils import get_templates

router = APIRouter(prefix="/idice", tags=["idice"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def idice_page(request: Request, db: Session = Depends(get_db)):
    metrics = [r[0] for r in db.query(MetricRecord.name).distinct().all()]
    return templates.TemplateResponse("idice.html", {
        "request": request, "metrics": metrics, "result": None,
    })


@router.post("/drill", response_class=HTMLResponse)
def idice_drill(
    request: Request,
    metric_name: str = Form(...),
    hours: int = Form(6),
    anomaly_threshold: float = Form(2.0),
    db: Session = Depends(get_db),
):
    since = datetime.now() - timedelta(hours=hours)
    records = (
        db.query(MetricRecord)
        .filter(MetricRecord.name == metric_name, MetricRecord.timestamp >= since)
        .order_by(MetricRecord.timestamp.desc())
        .all()
    )
    if not records:
        metrics = [r[0] for r in db.query(MetricRecord.name).distinct().all()]
        return templates.TemplateResponse("idice.html", {
            "request": request, "metrics": metrics, "error": "No data found",
        })

    values = [r.value for r in records]
    avg_val = sum(values) / len(values)
    std_val = (sum((v - avg_val) ** 2 for v in values) / len(values)) ** 0.5 or 1

    # Get assets with their attributes
    asset_ids = list(set(r.asset_id for r in records if r.asset_id))
    assets = {a.id: a for a in db.query(Asset).filter(Asset.id.in_(asset_ids)).all()} if asset_ids else {}

    # Build asset -> metric value mapping
    asset_values = defaultdict(list)
    for r in records:
        if r.asset_id:
            asset_values[r.asset_id].append(r.value)
    asset_avg = {aid: sum(vals) / len(vals) for aid, vals in asset_values.items() if vals}

    # Tag each asset as anomalous or not
    asset_anomaly = {}
    for aid, av in asset_avg.items():
        z = abs(av - avg_val) / std_val
        asset_anomaly[aid] = z > anomaly_threshold

    # Collect tag dimensions from assets
    tag_index = defaultdict(set)  # tag -> set of asset_ids
    type_index = defaultdict(set)  # ci_type -> set of asset_ids
    for aid, a in assets.items():
        for t in (a.tags or "").split(","):
            t = t.strip()
            if t:
                tag_index[t].add(aid)
        type_index[a.ci_type or a.type or "unknown"].add(aid)

    # Score each single dimension
    single_scores = []
    for dim_name, dim_set in tag_index.items():
        dim_assets = dim_set & set(asset_anomaly.keys())
        if not dim_assets:
            continue
        total = len(dim_assets)
        anom = sum(1 for a in dim_assets if asset_anomaly.get(a, False))
        ratio = anom / total if total > 0 else 0
        single_scores.append({
            "dimension": f"tag:{dim_name}", "total": total,
            "anomalous": anom, "ratio": round(ratio, 3),
        })
    for ci_type, type_set in type_index.items():
        type_assets = type_set & set(asset_anomaly.keys())
        if not type_assets:
            continue
        total = len(type_assets)
        anom = sum(1 for a in type_assets if asset_anomaly.get(a, False))
        ratio = anom / total if total > 0 else 0
        single_scores.append({
            "dimension": f"type:{ci_type}", "total": total,
            "anomalous": anom, "ratio": round(ratio, 3),
        })

    single_scores.sort(key=lambda x: -x["ratio"])

    # Explore 2-combinations of tags (iDice-like)
    combo_scores = []
    tags_list = list(tag_index.keys())
    if len(tags_list) >= 2:
        for t1, t2 in itertools.combinations(tags_list[:15], 2):
            combo_set = tag_index[t1] & tag_index[t2] & set(asset_anomaly.keys())
            if len(combo_set) < 2:
                continue
            total = len(combo_set)
            anom = sum(1 for a in combo_set if asset_anomaly.get(a, False))
            ratio = anom / total if total > 0 else 0
            combo_scores.append({
                "dimension": f"tag:{t1} + tag:{t2}", "total": total,
                "anomalous": anom, "ratio": round(ratio, 3),
            })
    combo_scores.sort(key=lambda x: -x["ratio"])

    metrics = [r[0] for r in db.query(MetricRecord.name).distinct().all()]
    return templates.TemplateResponse("idice.html", {
        "request": request, "metrics": metrics,
        "result": {
            "metric_name": metric_name,
            "total_assets": len(asset_anomaly),
            "anomalous_assets": sum(1 for v in asset_anomaly.values() if v),
            "global_avg": round(avg_val, 2),
            "global_std": round(std_val, 2),
            "threshold_z": anomaly_threshold,
            "single_dimensions": single_scores[:20],
            "combo_dimensions": combo_scores[:20],
        },
    })
