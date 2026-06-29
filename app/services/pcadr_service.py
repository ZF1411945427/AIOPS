import json
from datetime import datetime, timedelta
import numpy as np
from sqlalchemy.orm import Session
from app.models import Asset, MetricRecord, Alert, Incident


def run_pcadr(db: Session, incident_id: int = None, asset_id: int = None, hours: int = 6):
    """
    PCA-based root cause analysis:
    1. Collect metric data for assets involved in the incident
    2. Build a matrix of metrics x timepoints
    3. Apply PCA to find which metrics contribute most to variance
    4. Score each metric by its contribution to PC1 (largest variance component)
    """
    if incident_id:
        inc = db.query(Incident).filter(Incident.id == incident_id).first()
        if not inc:
            return {"error": "Incident not found"}
        related_alerts = db.query(Alert).filter(Alert.incident_id == incident_id).all()
        asset_ids = list(set(a.asset_id for a in related_alerts if a.asset_id))
        inc_title = inc.title
    elif asset_id:
        asset_ids = [asset_id]
        inc_title = f"Asset #{asset_id} PCADR Analysis"
    else:
        # Auto-analyze: pick assets with recent alerts
        recent = db.query(Alert).filter(
            Alert.created_at >= datetime.now() - timedelta(hours=hours),
            Alert.asset_id != None,
        ).all()
        asset_ids = list(set(a.asset_id for a in recent))
        inc_title = f"Auto PCADR Analysis (last {hours}h)"

    if not asset_ids:
        return {"error": "No assets with alerts found", "title": inc_title}

    since = datetime.now() - timedelta(hours=hours)
    metrics_data = (
        db.query(MetricRecord)
        .filter(MetricRecord.asset_id.in_(asset_ids), MetricRecord.timestamp >= since)
        .order_by(MetricRecord.timestamp)
        .all()
    )

    if not metrics_data:
        return {"error": "No metric data found", "title": inc_title}

    # Build pivot: metric_name -> list of values
    metric_values = {}
    timepoints = {}
    for m in metrics_data:
        key = f"{m.asset_id}_{m.name}"
        if key not in metric_values:
            metric_values[key] = []
            timepoints[key] = []
        metric_values[key].append(m.value)
        timepoints[key].append(m.timestamp.isoformat() if m.timestamp else "")

    # Ensure equal length - truncate to shortest
    min_len = min(len(v) for v in metric_values.values())
    if min_len < 3:
        return {"error": "Not enough data points for PCA (need >= 3)", "title": inc_title}

    matrix = []
    labels = []
    for key, vals in metric_values.items():
        labels.append(key)
        matrix.append(vals[:min_len])

    arr = np.array(matrix, dtype=float)
    # Center the data
    arr_centered = arr - arr.mean(axis=1, keepdims=True)
    # Fill NaN with 0
    arr_centered = np.nan_to_num(arr_centered)

    # PCA via SVD
    if arr_centered.shape[1] < 2:
        return {"error": "Need at least 2 timepoints after cleanup", "title": inc_title}

    try:
        U, S, Vt = np.linalg.svd(arr_centered, full_matrices=False)
    except np.linalg.LinAlgError:
        return {"error": "SVD failed - data may be degenerate", "title": inc_title}

    # PC1 loadings (contributions): absolute values of first right singular vector
    pc1 = Vt[0]
    pc1_contrib = np.abs(pc1)

    # Normalize contributions to percentage
    total_contrib = pc1_contrib.sum()
    if total_contrib > 0:
        pc1_pct = (pc1_contrib / total_contrib * 100).tolist()
    else:
        pc1_pct = [0] * len(pc1_contrib)

    # Variance explained
    total_var = S.sum()
    var_explained = [(s / total_var * 100) if total_var > 0 else 0 for s in S]

    # Sort metrics by contribution
    scored = sorted(zip(labels, pc1_pct, pc1_contrib.tolist()), key=lambda x: -x[1])

    # Get alert info for each asset-metric
    alerts_info = {}
    for a in db.query(Alert).filter(
        Alert.asset_id.in_(asset_ids),
        Alert.created_at >= since,
        Alert.status == "triggered",
    ).all():
        key = f"{a.asset_id}_{a.metric_name}"
        if key not in alerts_info:
            alerts_info[key] = []
        alerts_info[key].append(f"#{a.id}({a.severity}={a.actual_value})")

    scored_with_alerts = []
    for label, pct, raw in scored:
        info = alerts_info.get(label, [])
        scored_with_alerts.append({
            "metric": label, "contribution_pct": round(pct, 1),
            "raw_loading": round(raw, 4),
            "alerts": info,
        })

    result = {
        "title": inc_title,
        "asset_ids": asset_ids,
        "metric_count": len(labels),
        "timepoints": min_len,
        "variance_explained": [round(v, 1) for v in var_explained[:5]],
        "top_contributors": scored_with_alerts[:20],
        "total_metrics_analyzed": len(labels),
        "analysis_time": datetime.now().isoformat(),
    }
    return result
