from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import MetricRecord

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
    # R虏
    y_mean = sum_y / n
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    return slope, intercept, r2


def predict_capacity(db: Session, metric_name: str, hours_back: int = 168, threshold: float = None):
    """
    Predict capacity trend for a given metric.
    Returns dict with trend data, prediction, and estimated days until threshold.
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

    # Estimate days until threshold
    days_until = None
    if threshold and slope > 0:
        x_at_threshold = (threshold - intercept) / slope
        current_x = xs[-1]
        hours_until = (x_at_threshold - current_x)  # each x is ~1 hour
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
        svg += f'<text x="{width - padding - 5}" y="{ty - 5}" fill="#e67e22" font-size="11">闃堝€?{threshold}</text>'

    # Labels
    svg += f'<text x="{padding}" y="{height - 5}" fill="#999" font-size="10">鍘嗗彶</text>'
    if pred:
        svg += f'<text x="{padding + chart_w - 40}" y="{height - 5}" fill="#d94a4a" font-size="10">棰勬祴</text>'

    svg += "</svg>"
    return svg

