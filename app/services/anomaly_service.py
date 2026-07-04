import math
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AnomalyConfig, MetricRecord, Alert
from app.services import notification_service


def list_configs(db: Session):
    return db.query(AnomalyConfig).order_by(AnomalyConfig.id.desc()).all()


def get_config(db: Session, config_id: int):
    return db.query(AnomalyConfig).filter(AnomalyConfig.id == config_id).first()


def create_config(db: Session, data: dict):
    config = AnomalyConfig(**data)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def update_config(db: Session, config_id: int, data: dict):
    config = get_config(db, config_id)
    if not config:
        return None
    for k, v in data.items():
        setattr(config, k, v)
    db.commit()
    db.refresh(config)
    return config


def delete_config(db: Session, config_id: int):
    db.query(AnomalyConfig).filter(AnomalyConfig.id == config_id).delete()
    db.commit()


def toggle_config(db: Session, config_id: int):
    config = get_config(db, config_id)
    if config:
        config.enabled = not config.enabled
        db.commit()
        db.refresh(config)
    return config


def _has_recent_alert(db: Session, metric_name: str, asset_id: int, algorithm: str, config_name: str) -> bool:
    tag = f"{'EWMA' if algorithm == 'ewma' else '3σ'}异常"
    return bool(
        db.query(Alert)
        .filter(
            Alert.metric_name == metric_name,
            Alert.asset_id == (asset_id or 0),
            Alert.status.in_(["triggered", "acknowledged"]),
            Alert.message.like(f"%{tag}%"),
        )
        .first()
    )


def _detect_sigma(db: Session, config: AnomalyConfig, records: list) -> Alert | None:
    values = [r.value for r in records[:config.window_size]]
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    stddev = math.sqrt(variance)

    if stddev == 0:
        return None

    latest = records[0]
    z_score = abs(latest.value - mean) / stddev

    if z_score <= config.sensitivity:
        return None
    if _has_recent_alert(db, config.metric_name, config.asset_id, "sigma", config.name):
        return None

    is_high = latest.value > mean
    direction = "偏高" if is_high else "偏低"
    return Alert(
        rule_id=None,
        asset_id=config.asset_id or records[0].asset_id,
        metric_name=config.metric_name,
        actual_value=round(latest.value, 2),
        threshold=round(mean + config.sensitivity * stddev, 2),
        severity="warning" if z_score < 4 else "critical",
        status="triggered",
        message=f"3σ异常检测- {config.name}: {config.metric_name} {direction} (z={round(z_score,2)}, 均值={round(mean,2)}, σ={round(stddev,2)})",
    )


def _detect_ewma(db: Session, config: AnomalyConfig, records: list) -> Alert | None:
    alpha = 2.0 / (config.sensitivity + 1.0)
    alpha = min(max(alpha, 0.1), 0.9)

    values = [r.value for r in records]
    ewma = values[0]
    residuals = []

    for v in values:
        pred = ewma
        error = v - pred
        residuals.append(error)
        ewma = alpha * v + (1 - alpha) * ewma

    n = len(residuals)
    mean_res = sum(residuals) / n
    var_res = sum((r - mean_res) ** 2 for r in residuals) / n
    std_res = math.sqrt(var_res) if var_res > 0 else 0.0001

    latest = records[0]
    residual = latest.value - ewma
    norm_residual = abs(residual) / std_res

    threshold = 3.0
    if norm_residual <= threshold:
        return None
    if _has_recent_alert(db, config.metric_name, config.asset_id, "ewma", config.name):
        return None

    direction = "偏高" if residual > 0 else "偏低"
    return Alert(
        rule_id=None,
        asset_id=config.asset_id or records[0].asset_id,
        metric_name=config.metric_name,
        actual_value=round(latest.value, 2),
        threshold=round(ewma + threshold * std_res, 2),
        severity="warning" if norm_residual < 5 else "critical",
        status="triggered",
        message=f"EWMA异常检测- {config.name}: {config.metric_name} {direction} (残差={round(norm_residual,2)}, α={round(alpha,2)}, EWMA={round(ewma,2)})",
    )


def _detect_mad(db: Session, config: AnomalyConfig, records: list) -> Alert | None:
    """Median Absolute Deviation — robust to outliers vs 3-sigma."""
    values = sorted(r.value for r in records[:config.window_size])
    n = len(values)
    median = values[n // 2]
    abs_devs = sorted(abs(v - median) for v in values)
    mad = abs_devs[n // 2]
    if mad == 0:
        mad = sum(abs(v - median) for v in values[:max(2, n)]) / n
    if mad == 0:
        return None
    latest = records[0]
    modified_z = 0.6745 * (latest.value - median) / mad
    if abs(modified_z) <= config.sensitivity:
        return None
    if _has_recent_alert(db, config.metric_name, config.asset_id, "mad", config.name):
        return None
    direction = "偏高" if modified_z > 0 else "偏低"
    return Alert(
        rule_id=None,
        asset_id=config.asset_id or records[0].asset_id,
        metric_name=config.metric_name,
        actual_value=round(latest.value, 2),
        threshold=round(median, 2),
        severity="warning" if abs(modified_z) < 4 else "critical",
        status="triggered",
        message=f"MAD异常检测- {config.name}: {config.metric_name} {direction} (MAD-z={round(modified_z,2)}, 中位数={round(median,2)}, MAD={round(mad,2)})",
    )


def _detect_stl(db: Session, config: AnomalyConfig, records: list) -> Alert | None:
    values = [r.value for r in records]
    values.reverse()
    n = len(values)
    period = max(2, getattr(config, 'period', 12) or 12)
    if n < period * 2:
        return None

    trend = []
    half = period // 2
    for i in range(n):
        left = max(0, i - half)
        right = min(n, i + half + 1)
        trend.append(sum(values[left:right]) / (right - left))
    trend = [float('nan')] * half + trend[half:-half] + [float('nan')] * half
    for i in range(n):
        if i < half or i >= n - half:
            valid = [v for v in values[max(0,i-half):min(n,i+half+1)]]
            trend[i] = sum(valid) / len(valid) if valid else values[i]

    detrended = [values[i] - trend[i] for i in range(n)]
    seasonal = [0.0] * n
    for i in range(period):
        slice_vals = [detrended[j] for j in range(i, n, period)]
        avg = sum(slice_vals) / len(slice_vals) if slice_vals else 0
        for j in range(i, n, period):
            seasonal[j] = avg
    seasonal_mean = sum(seasonal[:period]) / period
    seasonal = [s - seasonal_mean for s in seasonal]

    residual = [values[i] - trend[i] - seasonal[i] for i in range(n)]

    resid_valid = [r for r in residual if not math.isnan(r)]
    if len(resid_valid) < 3:
        return None
    mean_r = sum(resid_valid) / len(resid_valid)
    var_r = sum((r - mean_r) ** 2 for r in resid_valid) / len(resid_valid)
    std_r = math.sqrt(var_r) if var_r > 0 else 0.0001

    latest_residual = residual[-1]
    latest_value = values[-1]
    z_score = abs(latest_residual - mean_r) / std_r

    if z_score <= config.sensitivity:
        return None
    if _has_recent_alert(db, config.metric_name, config.asset_id, "stl", config.name):
        return None

    direction = "偏高" if latest_residual > 0 else "偏低"
    return Alert(
        rule_id=None,
        asset_id=config.asset_id or records[0].asset_id,
        metric_name=config.metric_name,
        actual_value=round(latest_value, 2),
        threshold=round(trend[-1] + seasonal[-1] + config.sensitivity * std_r, 2),
        severity="warning" if z_score < 4 else "critical",
        status="triggered",
        message=f"STL异常检测- {config.name}: {config.metric_name} {direction} (z={round(z_score,2)}, 周期={period})",
    )


def _detect_prophet(db: Session, config: AnomalyConfig, records: list) -> Alert | None:
    try:
        from prophet import Prophet
    except ImportError:
        return None
    values = [r.value for r in records]
    timestamps = [r.timestamp for r in records]
    if len(values) < 10:
        return None
    import pandas as pd
    df = pd.DataFrame({"ds": pd.to_datetime(timestamps), "y": values})
    model = Prophet(yearly_seasonality=False, weekly_seasonality=False, daily_seasonality=True)
    model.fit(df)
    future = model.make_future_dataframe(periods=0, include_history=True)
    forecast = model.predict(future)
    merged = df.merge(forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]], on="ds")
    anomalies = merged[merged["y"] > merged["yhat_upper"]]
    if anomalies.empty:
        return None
    latest = anomalies.iloc[-1]
    return Alert(
        name=f"Prophet-{config.name}",
        metric=config.metric_name,
        message=f"Prophet异常检测- {config.name}: 最新值={round(latest['y'],2)}, "
                f"上限={round(latest['yhat_upper'],2)}, 预测={round(latest['yhat'],2)}",
        severity="warning",
        asset_id=config.asset_id,
        source="prophet",
    )


def _detect_lstm(db: Session, config: AnomalyConfig, records: list) -> Alert | None:
    """Simple numpy-based sliding window prediction simulating LSTM behavior."""
    import numpy as np
    values = np.array([r.value for r in records])
    if len(values) < 10:
        return None
    window = max(3, len(values) // 4)
    predictions = []
    actuals = []
    for i in range(window, len(values)):
        x = values[i - window:i]
        y = values[i]
        w = np.arange(window)
        slope = (np.sum(w * x) - window * np.mean(w) * np.mean(x)) / (np.sum(w ** 2) - window * np.mean(w) ** 2) if (np.sum(w ** 2) - window * np.mean(w) ** 2) != 0 else 0
        intercept = np.mean(x) - slope * np.mean(w)
        pred = slope * window + intercept
        predictions.append(pred)
        actuals.append(y)
    if not predictions:
        return None
    preds = np.array(predictions)
    acts = np.array(actuals)
    residuals = np.abs(acts - preds)
    threshold = np.mean(residuals) + 2 * np.std(residuals)
    latest_residual = residuals[-1]
    if latest_residual > threshold and latest_residual > np.mean(residuals) * 1.5:
        return Alert(
            name=f"LSTM-{config.name}",
            metric=config.metric_name,
            message=f"LSTM预测异常- {config.name}: 实际={round(acts[-1],2)}, "
                    f"预测={round(preds[-1],2)}, 残差={round(latest_residual,2)}",
            severity="warning",
            asset_id=config.asset_id,
            source="lstm",
        )
    return None


def _detect_transformer(db: Session, config: AnomalyConfig, records: list) -> Alert | None:
    """Simple self-attention style anomaly detection using numpy."""
    import numpy as np
    values = np.array([r.value for r in records])
    if len(values) < 10:
        return None
    n = len(values)
    d = 4
    Q = np.column_stack([np.roll(values, i) for i in range(d)]) if n >= d else None
    if Q is None or np.any(np.isnan(Q)):
        return None
    Q = Q[:n-d+1] if n > d else Q
    K = Q.copy()
    V = Q[:, 0:1].copy()
    scores = np.dot(Q, K.T) / np.sqrt(d)
    weights = np.exp(scores - np.max(scores, axis=1, keepdims=True))
    weights = weights / np.sum(weights, axis=1, keepdims=True)
    attn_output = np.dot(weights, V).flatten()
    residuals = np.abs(values[d-1:d-1+len(attn_output)] - attn_output)
    if len(residuals) < 3:
        return None
    threshold = np.mean(residuals) + 2 * np.std(residuals)
    if residuals[-1] > threshold:
        return Alert(
            name=f"Transformer-{config.name}",
            metric=config.metric_name,
            message=f"Transformer异常检测- {config.name}: 残差={round(residuals[-1],2)}, "
                    f"阈值={round(threshold,2)}",
            severity="warning",
            asset_id=config.asset_id,
            source="transformer",
        )
    return None


def detect_anomalies(db: Session):
    configs = db.query(AnomalyConfig).filter(AnomalyConfig.enabled == True).all()
    new_alerts = []

    for config in configs:
        cfg_alg = getattr(config, 'algorithm', None) or 'sigma'
        q = db.query(MetricRecord).filter(MetricRecord.name == config.metric_name)
        if config.asset_id:
            q = q.filter(MetricRecord.asset_id == config.asset_id)
        records = q.order_by(MetricRecord.timestamp.desc()).limit(config.window_size + 5).all()

        if len(records) < config.window_size:
            continue

        if cfg_alg == 'ewma':
            alert = _detect_ewma(db, config, records)
        elif cfg_alg == 'stl':
            alert = _detect_stl(db, config, records)
        elif cfg_alg == 'mad':
            alert = _detect_mad(db, config, records)
        elif cfg_alg == 'prophet':
            try:
                alert = _detect_prophet(db, config, records)
            except Exception:
                alert = None
        elif cfg_alg == 'lstm':
            try:
                alert = _detect_lstm(db, config, records)
            except Exception:
                alert = None
        elif cfg_alg == 'transformer':
            try:
                alert = _detect_transformer(db, config, records)
            except Exception:
                alert = None
        else:
            alert = _detect_sigma(db, config, records)

        if alert:
            db.add(alert)
            new_alerts.append(alert)

    if new_alerts:
        db.commit()
        for a in new_alerts:
            db.refresh(a)
        notification_service.notify_new_alerts(db, new_alerts)
    return new_alerts


