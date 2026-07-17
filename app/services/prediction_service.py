import json
import math
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from app.models import MetricRecord, PredictionModel, FeatureStoreItem


def linear_regression(xs, ys):
    """Simple linear regression: y = slope * x + intercept. Returns (slope, intercept, r2)."""
    n = len(xs)
    if n < 2:
        return 0, 0, 0
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_xx = sum(x * x for x in xs)
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return 0, sum_y / n, 0
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    y_mean = sum_y / n
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    return slope, intercept, r2


def polynomial_regression(xs, ys, degree=2):
    """Polynomial regression using least squares. Returns coefficients and r2."""
    n = len(xs)
    if n < degree + 1:
        return None, 0
    # Build Vandermonde matrix
    X = [[x ** d for d in range(degree + 1)] for x in xs]
    # X^T * X
    XtX = [[sum(X[i][d1] * X[i][d2] for i in range(n)) for d2 in range(degree + 1)] for d1 in range(degree + 1)]
    # X^T * y
    Xty = [sum(X[i][d] * ys[i] for i in range(n)) for d in range(degree + 1)]
    # Solve using Gaussian elimination
    aug = [XtX[i] + [Xty[i]] for i in range(degree + 1)]
    for i in range(degree + 1):
        max_row = i
        for k in range(i + 1, degree + 1):
            if abs(aug[k][i]) > abs(aug[max_row][i]):
                max_row = k
        aug[i], aug[max_row] = aug[max_row], aug[i]
        if abs(aug[i][i]) < 1e-10:
            continue
        for k in range(i + 1, degree + 1):
            factor = aug[k][i] / aug[i][i]
            for j in range(i, degree + 2):
                aug[k][j] -= factor * aug[i][j]
    coeffs = [0] * (degree + 1)
    for i in range(degree + 1, -1, -1):
        if i >= len(aug) or abs(aug[i][i]) < 1e-10:
            continue
        coeffs[i] = aug[i][-1]
        for j in range(i + 1, degree + 1):
            coeffs[i] -= aug[i][j] * coeffs[j]
        coeffs[i] /= aug[i][i]
    # Calculate R2
    y_mean = sum(ys) / n
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((ys[i] - sum(coeffs[d] * xs[i] ** d for d in range(degree + 1))) ** 2 for i in range(n))
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    return coeffs, r2


def rolling_average(values, window=20):
    """Calculate rolling average. Returns list of averaged values."""
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        result.append(sum(values[start:i + 1]) / (i - start + 1))
    return result


def get_metric_data(db: Session, metric_name: str, asset_id: Optional[int] = None,
                    hours_back: int = 168) -> List[Dict]:
    """Get metric data aggregated by hour."""
    since = datetime.now() - timedelta(hours=hours_back)
    query = db.query(MetricRecord).filter(
        MetricRecord.name == metric_name,
        MetricRecord.timestamp >= since
    )
    if asset_id:
        query = query.filter(MetricRecord.asset_id == asset_id)
    records = query.order_by(MetricRecord.timestamp.asc()).all()

    hourly = {}
    for r in records:
        key = r.timestamp.replace(minute=0, second=0, microsecond=0)
        if key not in hourly:
            hourly[key] = []
        hourly[key].append(r.value)

    hours = sorted(hourly.keys())
    values = [sum(hourly[h]) / len(hourly[h]) for h in hours]
    return [{"timestamp": h.isoformat(), "value": v} for h, v in zip(hours, values)]


def get_features_for_prediction(db: Session, metric_name: str, asset_id: Optional[int] = None) -> Dict:
    """Get relevant features from feature store for prediction."""
    features = {}
    # Map metric names to feature names
    feature_mapping = {
        "cpu_usage": ["cpu_avg_1h", "cpu_avg_24h"],
        "memory_usage": ["mem_avg_1h", "mem_avg_24h"],
        "disk_usage": ["disk_avg_1h", "disk_avg_24h"],
        "network_in": ["network_in_avg_1h"],
        "network_out": ["network_out_avg_1h"],
    }
    feature_names = feature_mapping.get(metric_name, [])

    for fname in feature_names:
        query = db.query(FeatureStoreItem).filter(FeatureStoreItem.feature_name == fname)
        if asset_id:
            query = query.filter(FeatureStoreItem.entity_id == asset_id)
        item = query.order_by(FeatureStoreItem.created_at.desc()).first()
        if item:
            features[fname] = {
                "value": item.feature_value,
                "source": item.source,
                "updated_at": item.created_at.isoformat() if item.created_at else None
            }
    return features


def predict_with_model(db: Session, model: PredictionModel, hours_back: int = 168) -> Optional[Dict]:
    """Execute prediction using a configured model."""
    params = json.loads(model.model_params) if isinstance(model.model_params, str) else model.model_params
    window = params.get("window", 20)
    threshold = params.get("threshold")
    degree = params.get("degree", 2)

    # Get metric data
    data = get_metric_data(db, model.metric_name, model.asset_id, hours_back)
    if len(data) < 5:
        return None

    values = [d["value"] for d in data]
    timestamps = [d["timestamp"] for d in data]
    xs = list(range(len(values)))

    # Get features for context
    features = get_features_for_prediction(db, model.metric_name, model.asset_id)

    # Apply model type
    if model.model_type in ("linear", "arima"):
        # ARIMA simplified: use linear regression with differencing
        if len(values) > 1:
            # First difference for stationarity
            diff_values = [values[i] - values[i-1] for i in range(1, len(values))]
            diff_xs = list(range(len(diff_values)))
            slope, intercept, r2 = linear_regression(diff_xs, diff_values)
            # Integrate back
            last_value = values[-1]
            future_count = 168
            pred_values = []
            current = last_value
            for i in range(future_count):
                current += slope
                pred_values.append(current)
        else:
            slope, intercept, r2 = linear_regression(xs, values)
            future_count = 168
            last_x = xs[-1]
            pred_xs = list(range(last_x + 1, last_x + 1 + future_count))
            pred_values = [slope * x + intercept for x in pred_xs]

        pred_timestamps = [
            (datetime.now() + timedelta(hours=i + 1)).isoformat()
            for i in range(future_count)
        ]
        trend = "increasing" if slope > 0.001 else "decreasing" if slope < -0.001 else "stable"

    elif model.model_type == "polynomial":
        coeffs, r2 = polynomial_regression(xs, values, degree)
        if coeffs is None:
            return None
        future_count = 168
        last_x = xs[-1]
        pred_xs = list(range(last_x + 1, last_x + 1 + future_count))
        pred_values = [sum(coeffs[d] * x ** d for d in range(len(coeffs))) for x in pred_xs]
        pred_timestamps = [
            (datetime.now() + timedelta(hours=i + 1)).isoformat()
            for i in range(future_count)
        ]
        if len(pred_values) > 1:
            diff = pred_values[-1] - pred_values[0]
            trend = "increasing" if diff > 1 else "decreasing" if diff < -1 else "stable"
        else:
            trend = "stable"
        slope = (pred_values[-1] - pred_values[0]) / future_count if future_count > 0 else 0

    elif model.model_type == "rolling_avg":
        avg_values = rolling_average(values, window)
        baseline = avg_values[-1] if avg_values else 0
        future_count = 168
        pred_values = [baseline] * future_count
        pred_timestamps = [
            (datetime.now() + timedelta(hours=i + 1)).isoformat()
            for i in range(future_count)
        ]
        if len(values) > window:
            recent_avg = sum(values[-window:]) / window
            older_avg = sum(values[-2 * window:-window]) / window if len(values) > 2 * window else recent_avg
            diff = recent_avg - older_avg
            trend = "increasing" if diff > 1 else "decreasing" if diff < -1 else "stable"
        else:
            trend = "stable"
        slope = 0
        r2 = 0

    elif model.model_type == "prophet":
        # Prophet simplified: use weighted moving average with trend
        if len(values) > window:
            # Calculate trend from recent data
            recent = values[-window:]
            older = values[-2*window:-window] if len(values) > 2*window else values[:window]
            recent_avg = sum(recent) / len(recent)
            older_avg = sum(older) / len(older)
            trend_slope = (recent_avg - older_avg) / window
            # Predict with trend
            future_count = 168
            pred_values = []
            for i in range(future_count):
                pred_values.append(recent_avg + trend_slope * (i + 1))
            slope = trend_slope
        else:
            slope, intercept, r2 = linear_regression(xs, values)
            future_count = 168
            last_x = xs[-1]
            pred_xs = list(range(last_x + 1, last_x + 1 + future_count))
            pred_values = [slope * x + intercept for x in pred_xs]

        pred_timestamps = [
            (datetime.now() + timedelta(hours=i + 1)).isoformat()
            for i in range(future_count)
        ]
        trend = "increasing" if slope > 0.001 else "decreasing" if slope < -0.001 else "stable"
        r2 = 0  # Not calculated for this simplified version

    else:
        return None

    # Estimate days expires_at threshold
    days_until = None
    if threshold and slope > 0:
        current_value = values[-1]
        if current_value < threshold:
            hours_until = (threshold - current_value) / slope
            if hours_until > 0:
                days_until = round(hours_until / 24, 1)

    return {
        "model_id": model.id,
        "model_name": model.name,
        "metric_name": model.metric_name,
        "model_type": model.model_type,
        "current_value": values[-1] if values else 0,
        "trend": trend,
        "slope": slope,
        "r2": r2 if 'r2' in locals() else 0,
        "data_points": len(values),
        "history": {
            "timestamps": timestamps[-48:],  # Last 48 hours
            "values": values[-48:]
        },
        "prediction": {
            "timestamps": pred_timestamps[:48],  # Next 48 hours
            "values": pred_values[:48]
        },
        "days_until_threshold": days_until,
        "threshold": threshold,
        "features": features,
        "params": params,
        "predicted_at": datetime.now().isoformat()
    }


def predict_capacity(db: Session, metric_name: str, hours_back: int = 168, threshold: float = None):
    """
    Predict capacity trend for a given metric (legacy function).
    Returns dict with trend data, prediction, and estimated days expires_at threshold.
    """
    since = datetime.now() - timedelta(hours=hours_back)
    records = (
        db.query(MetricRecord)
        .filter(MetricRecord.name == metric_name, MetricRecord.timestamp >= since)
        .order_by(MetricRecord.timestamp.asc())
        .all()
    )
    if len(records) < 5:
        return None

    # Aggregate by hour to reduce noise
    hourly = {}
    for r in records:
        key = r.timestamp.replace(minute=0, second=0, microsecond=0)
        if key not in hourly:
            hourly[key] = []
        hourly[key].append(r.value)
    hours = sorted(hourly.keys())
    values = [sum(hourly[h]) / len(hourly[h]) for h in hours]

    # Linear regression on hour index
    xs = list(range(len(hours)))
    slope, intercept, r2 = linear_regression(xs, values)
    if slope <= 0 and threshold:
        return {
            "metric": metric_name,
            "slope": slope,
            "intercept": intercept,
            "r2": r2,
            "hours": [h.isoformat() for h in hours],
            "values": values,
            "prediction": None,
            "days_until_threshold": None,
            "trend": "stable_or_decreasing",
            "current_value": values[-1] if values else 0,
            "threshold": threshold,
            "data_points": len(records),
        }

    # Predict forward 7 days (168 hours)
    future_hours_count = 168
    last_x = xs[-1]
    pred_xs = list(range(last_x + 1, last_x + 1 + future_hours_count))
    pred_ys = [slope * x + intercept for x in pred_xs]

    # Estimate days expires_at threshold
    days_until = None
    if threshold and slope > 0:
        x_at_threshold = (threshold - intercept) / slope
        current_x = xs[-1]
        hours_until = (x_at_threshold - current_x)
        if hours_until > 0:
            days_until = round(hours_until / 24, 1)

    return {
        "metric": metric_name,
        "slope": slope,
        "intercept": intercept,
        "r2": r2,
        "hours": [h.isoformat() for h in hours],
        "values": values,
        "prediction": {"hours": list(range(len(hours), len(hours) + future_hours_count)), "values": pred_ys},
        "days_until_threshold": days_until,
        "trend": "increasing" if slope > 0.001 else "decreasing" if slope < -0.001 else "stable",
        "current_value": values[-1] if values else 0,
        "threshold": threshold,
        "data_points": len(records),
    }


def get_predictable_metrics(db: Session):
    """Get metric names that have enough data for prediction."""
    from sqlalchemy import text
    rs = db.execute(text("""
        SELECT name, COUNT(*) as cnt, MIN(timestamp) as oldest, MAX(value) as max_val
        FROM metric_records
        GROUP BY name
        HAVING cnt >= 10
        ORDER BY cnt DESC
    """))
    return [{"name": r.name, "count": r.cnt, "oldest": r.oldest, "max_value": r.max_val} for r in rs]


def generate_trend_svg(data):
    """Generate an inline SVG sparkline for the trend data."""
    if not data or not data.get("values"):
        return ""
    values = data["values"]
    pred = data.get("prediction")

    width = 600
    height = 200
    padding = 40
    chart_w = width - 2 * padding
    chart_h = height - 2 * padding

    all_vals = values[:]
    if pred:
        all_vals.extend(pred["values"])

    min_v = min(all_vals) if all_vals else 0
    max_v = max(all_vals) if all_vals else 1
    if max_v == min_v:
        max_v = min_v + 1
    range_v = max_v - min_v

    def point(i, v):
        x = padding + (i / max(1, len(all_vals) - 1)) * chart_w if len(all_vals) > 1 else padding + chart_w / 2
        y = padding + chart_h - ((v - min_v) / range_v) * chart_h
        return f"{x},{y}"

    # Historical line
    hist_points = " ".join(point(i, v) for i, v in enumerate(values))
    svg = f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" style="background:#f8f9fa;border-radius:8px">'
    svg += f'<polyline points="{hist_points}" fill="none" stroke="#4a90d9" stroke-width="2"/>'

    # Prediction line (dashed)
    if pred:
        pred_points = " ".join(point(len(values) + i, v) for i, v in enumerate(pred["values"]))
        svg += f'<polyline points="{pred_points}" fill="none" stroke="#d94a4a" stroke-width="2" stroke-dasharray="5,3"/>'
        # Vertical separator
        sep_x = padding + (len(values) / max(1, len(all_vals) - 1)) * chart_w
        svg += f'<line x1="{sep_x}" y1="{padding}" x2="{sep_x}" y2="{height - padding}" stroke="#ccc" stroke-width="1" stroke-dasharray="3,3"/>'

    # Threshold line
    threshold = data.get("threshold")
    if threshold and min_v <= threshold <= max_v:
        ty = padding + chart_h - ((threshold - min_v) / range_v) * chart_h
        svg += f'<line x1="{padding}" y1="{ty}" x2="{width - padding}" y2="{ty}" stroke="#e67e22" stroke-width="1" stroke-dasharray="4,2"/>'
        svg += f'<text x="{width - padding - 5}" y="{ty - 5}" fill="#e67e22" font-size="11">阈值: {threshold}</text>'

    # Labels
    svg += f'<text x="{padding}" y="{height - 5}" fill="#999" font-size="10">历史</text>'
    if pred:
        svg += f'<text x="{padding + chart_w - 40}" y="{height - 5}" fill="#d94a4a" font-size="10">预测</text>'

    svg += "</svg>"
    return svg
