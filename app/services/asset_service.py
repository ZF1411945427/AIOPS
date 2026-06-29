from sqlalchemy.orm import Session

from app.models import Asset


def list_assets(db: Session, search: str = "", type: str = "", ci_type: str = ""):
    q = db.query(Asset)
    if search:
        q = q.filter(Asset.name.ilike(f"%{search}%"))
    if type:
        q = q.filter(Asset.type == type)
    if ci_type:
        q = q.filter(Asset.ci_type == ci_type)
    return q.order_by(Asset.id.desc()).all()


def list_by_ci_type(db: Session, ci_type: str):
    return db.query(Asset).filter(Asset.ci_type == ci_type).order_by(Asset.name).all()


def get_asset(db: Session, asset_id: int):
    return db.query(Asset).filter(Asset.id == asset_id).first()


def create_asset(db: Session, data: dict):
    asset = Asset(**data)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def update_asset(db: Session, asset_id: int, data: dict):
    asset = get_asset(db, asset_id)
    if not asset:
        return None
    try:
        from app.services.asset_change_service import log_change
        for k, v in data.items():
            old = str(getattr(asset, k, ""))
            setattr(asset, k, v)
            if str(v) != old:
                log_change(db, asset_id, k, old, str(v), "user")
    except Exception:
        for k, v in data.items():
            setattr(asset, k, v)
    db.commit()
    db.refresh(asset)
    return asset


def delete_asset(db: Session, asset_id: int):
    asset = get_asset(db, asset_id)
    if not asset:
        return False
    db.query(Asset).filter(Asset.parent_id == asset_id).update({"parent_id": None})
    db.delete(asset)
    db.commit()
    return True




def probe_assets(db: Session):
    """批量探测所有资产的连接状态，更新 status / last_checked / latency_ms"""
    from app.services.connection_service import ConnectionTester
    from datetime import datetime
    import json

    assets = db.query(Asset).all()
    changed = []
    for asset in assets:
        if not asset.ip:
            continue
        # 解析连接配置
        config = {}
        try:
            raw = asset.connection_config
            if isinstance(raw, str):
                config = json.loads(raw) if raw else {}
            else:
                config = raw or {}
        except (json.JSONDecodeError, TypeError):
            config = {}

        result = ConnectionTester.test(asset.connection_type or "ssh", asset.ip, config)
        old_status = asset.status
        new_status = "online" if result.get("ok") else "offline"
        asset.status = new_status
        asset.last_checked = datetime.now()
        asset.latency_ms = int(result.get("latency_ms", 0)) if result.get("ok") else None

        if old_status != new_status:
            changed.append({"id": asset.id, "name": asset.name,
                            "old": old_status, "new": new_status,
                            "message": result.get("message", "")})

    db.commit()
    return changed
