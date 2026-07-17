from datetime import datetime
from sqlalchemy.orm import Session
from app.models import AssetChangeLog, Asset, Alert
from app.services import metric_v2_service


def log_change(db: Session, asset_id: int, field: str, old_value: str, new_value: str, operator: str = "system"):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    log = AssetChangeLog(
        asset_id=asset_id,
        asset_name=asset.name if asset else "",
        field=field,
        old_value=str(old_value),
        new_value=str(new_value),
        operator=operator,
    )
    db.add(log)
    db.commit()


def get_change_logs(db: Session, asset_id: int = None, limit: int = 100):
    q = db.query(AssetChangeLog)
    if asset_id:
        q = q.filter(AssetChangeLog.asset_id == asset_id)
    return q.order_by(AssetChangeLog.created_at.desc()).limit(limit).all()


def scan_asset_health_changes(db: Session):
    """扫描所有资产健康状态变化，自动写入变更日志."""
    assets = db.query(Asset).filter(Asset.status == "online").all()
    changed = 0
    for asset in assets:
        old_health = getattr(asset, "health_status", "green")
        new_health = _compute_asset_health(db, asset)
        if old_health != new_health:
            log_change(db, asset.id, "health_status", old_health, new_health, operator="system:health_scan")
            asset.health_status = new_health
            changed += 1
    if changed:
        db.commit()
    return changed


def _compute_asset_health(db: Session, asset: Asset) -> str:
    """根据 VM 实时指标 + 活跃告警计算资产健康状态（green/yellow/red）."""
    triggered = (
        db.query(Alert)
        .filter(Alert.asset_id == asset.id, Alert.status == "triggered")
        .count()
    )
    if triggered > 0:
        return "red"

    try:
        latest = metric_v2_service.query_latest_values(asset_id=asset.id)
    except Exception:
        latest = {}

    cpu = latest.get("cpu_usage", {}).get("value", 0)
    mem = latest.get("memory_usage", {}).get("value", 0)
    disk = latest.get("disk_usage", {}).get("value", 0)

    unhealthy = sum(1 for v in [cpu, mem, disk] if v is not None and v > 80)
    if unhealthy >= 2:
        return "yellow"
    if unhealthy == 1:
        return "yellow"

    return "green"


def get_asset_health_score(db: Session, asset_id: int) -> dict:
    """计算单个资产的健康分（0-100）."""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return {"score": 0, "status": "unknown", "details": {}}

    triggered = (
        db.query(Alert)
        .filter(Alert.asset_id == asset_id, Alert.status == "triggered")
        .count()
    )
    acknowledged = (
        db.query(Alert)
        .filter(Alert.asset_id == asset_id, Alert.status == "acknowledged")
        .count()
    )

    base_score = 40 if asset.status == "online" else 0

    try:
        latest = metric_v2_service.query_latest_values(asset_id=asset_id)
    except Exception:
        latest = {}

    cpu = latest.get("cpu_usage", {}).get("value")
    mem = latest.get("memory_usage", {}).get("value")
    disk = latest.get("disk_usage", {}).get("value")

    cpu_score = 0
    mem_score = 0
    disk_score = 0
    if cpu is not None:
        cpu_score = max(0, 20 - (cpu / 5))
    if mem is not None:
        mem_score = max(0, 20 - (mem / 5))
    if disk is not None:
        disk_score = max(0, 20 - (disk / 5))

    alert_penalty = min(triggered * 10, 20)
    ack_penalty = min(acknowledged * 2, 10)

    score = max(0, min(100, base_score + cpu_score + mem_score + disk_score - alert_penalty - ack_penalty))

    status = "healthy" if score >= 80 else "warning" if score >= 50 else "danger"

    return {
        "score": round(score, 1),
        "status": status,
        "asset_id": asset_id,
        "asset_name": asset.name,
        "details": {
            "cpu": cpu,
            "memory": mem,
            "disk": disk,
            "triggered_alerts": triggered,
            "acknowledged_alerts": acknowledged,
            "online": asset.status == "online",
        }
    }


def get_all_asset_health(db: Session) -> list:
    """批量计算所有资产健康分."""
    assets = db.query(Asset).all()
    return [get_asset_health_score(db, a.id) for a in assets]
