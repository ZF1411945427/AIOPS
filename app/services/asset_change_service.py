from datetime import datetime
from sqlalchemy.orm import Session
from app.models import AssetChangeLog, Asset


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
