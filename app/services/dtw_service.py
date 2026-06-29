import numpy as np
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import MetricRecord, Asset


def dtw_distance(s1: list[float], s2: list[float]) -> float:
    """Dynamic Time Warping between two sequences."""
    n, m = len(s1), len(s2)
    dtw = np.full((n + 1, m + 1), np.inf)
    dtw[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = abs(s1[i - 1] - s2[j - 1])
            dtw[i, j] = cost + min(dtw[i - 1, j], dtw[i, j - 1], dtw[i - 1, j - 1])
    return dtw[n, m]


def find_similar_metrics(db: Session, metric_name: str, asset_id: int = None,
                         hours: int = 6, top_k: int = 10) -> list[dict]:
    since = datetime.now() - timedelta(hours=hours)
    q = db.query(MetricRecord).filter(MetricRecord.name == metric_name)
    if asset_id:
        q = q.filter(MetricRecord.asset_id == asset_id)
    target_records = q.order_by(MetricRecord.timestamp).all()
    if len(target_records) < 5:
        return []

    target_vals = [r.value for r in target_records]
    target_id = target_records[0].asset_id

    # Get all other metrics
    other_metrics = (
        db.query(MetricRecord.name, MetricRecord.asset_id)
        .filter(MetricRecord.timestamp >= since)
        .distinct()
        .all()
    )
    seen = set()
    results = []
    for name, aid in other_metrics:
        key = (name, aid)
        if key in seen or (name == metric_name and aid == target_id):
            continue
        seen.add(key)
        rows = (
            db.query(MetricRecord)
            .filter(MetricRecord.name == name, MetricRecord.asset_id == aid,
                    MetricRecord.timestamp >= since)
            .order_by(MetricRecord.timestamp)
            .all()
        )
        if len(rows) < 5:
            continue
        vals = [r.value for r in rows]
        # Align lengths
        min_len = min(len(target_vals), len(vals))
        if min_len < 5:
            continue
        dist = dtw_distance(target_vals[:min_len], vals[:min_len])
        # Normalize by length
        norm_dist = dist / min_len
        asset_name = db.query(Asset).filter(Asset.id == aid).first()
        results.append({
            "metric_name": name,
            "asset_id": aid,
            "asset_name": asset_name.name if asset_name else str(aid),
            "distance": round(norm_dist, 4),
            "length": min_len,
        })

    results.sort(key=lambda x: x["distance"])
    return results[:top_k]
