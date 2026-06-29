import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import MetricRecord, Asset


METRICS = [
    {"name": "cpu_usage", "unit": "%", "min": 10, "max": 95},
    {"name": "memory_usage", "unit": "%", "min": 20, "max": 90},
    {"name": "disk_usage", "unit": "%", "min": 10, "max": 98},
    {"name": "network_in", "unit": "Mbps", "min": 1, "max": 500},
    {"name": "network_out", "unit": "Mbps", "min": 1, "max": 300},
]


def simulate_metrics(db: Session):
    """仅在 demo 模式下生成模拟指标数据，REAL 模式不生成假数据"""
    from app.database import get_db_mode
    if get_db_mode() != "demo":
        return  # REAL 模式跳过，不生成假数据
    assets = db.query(Asset).filter(Asset.status == "online").all()
    now = datetime.now()
    for asset in assets:
        for m in METRICS:
            value = round(random.uniform(m["min"], m["max"]), 2)
            record = MetricRecord(
                asset_id=asset.id,
                name=m["name"],
                value=value,
                unit=m["unit"],
                timestamp=now,
            )
            db.add(record)
    db.commit()


def list_metrics(db: Session, asset_id: int = 0, name: str = "", hours: int = 1):
    q = db.query(MetricRecord)
    if asset_id:
        q = q.filter(MetricRecord.asset_id == asset_id)
    if name:
        q = q.filter(MetricRecord.name == name)
    since = datetime.now() - timedelta(hours=hours)
    q = q.filter(MetricRecord.timestamp >= since)
    return q.order_by(MetricRecord.timestamp.asc()).all()


def get_latest_metrics(db: Session):
    assets = db.query(Asset).filter(Asset.status == "online").all()
    result = {}
    for asset in assets:
        latest = (
            db.query(MetricRecord)
            .filter(MetricRecord.asset_id == asset.id)
            .order_by(MetricRecord.timestamp.desc())
            .limit(5)
            .all()
        )
        result[asset.id] = {"asset": asset, "metrics": {}}
        for m in latest:
            if m.name not in result[asset.id]["metrics"]:
                result[asset.id]["metrics"][m.name] = m
    return result


def get_metric_names(db: Session = None):
    if db:
        names = [r[0] for r in db.query(MetricRecord.name).distinct().order_by(MetricRecord.name).all()]
        if names:
            return names
    return [m["name"] for m in METRICS]


