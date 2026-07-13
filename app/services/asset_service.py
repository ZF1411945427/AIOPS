from sqlalchemy.orm import Session

from app.models import Asset
from app.database import get_session_for, get_db_mode


def list_assets(db: Session, search: str = "", type: str = "", ci_type: str = ""):
    q = db.query(Asset)
    if search:
        q = q.filter(Asset.name.ilike(f"%{search}%"))
    if type:
        q = q.filter(Asset.type == type)
    if ci_type:
        types = [t.strip() for t in ci_type.split(",") if t.strip()]
        if len(types) == 1:
            q = q.filter(Asset.ci_type == types[0])
        elif types:
            q = q.filter(Asset.ci_type.in_(types))
    return q.order_by(Asset.id.desc()).all()


def list_assets_paged(db: Session, search: str = "", type: str = "", ci_type: str = "", page: int = 1, page_size: int = 20):
    q = db.query(Asset)
    if search:
        q = q.filter(Asset.name.ilike(f"%{search}%"))
    if type:
        q = q.filter(Asset.type == type)
    if ci_type:
        types = [t.strip() for t in ci_type.split(",") if t.strip()]
        if len(types) == 1:
            q = q.filter(Asset.ci_type == types[0])
        elif types:
            q = q.filter(Asset.ci_type.in_(types))
    total = q.count()
    assets = q.order_by(Asset.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return assets, total


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
    from app.logger import logger
    from datetime import datetime
    import json
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    assets = db.query(Asset).all()
    changed = []

    # 为每个资产新建独立 Session，线程安全地并行探测
    # ThreadPoolExecutor 最多 10 并发，防止大量离线资产 SSH 超时串行拖垮总耗时
    _probe_db_factory = lambda: get_session_for(get_db_mode())()
    _lock = threading.Lock()

    def _probe_one(asset):
        if not asset.ip:
            return None
        # 用独立 Session 避免跨线程共用
        sess = _probe_db_factory()
        try:
            # 重新从 DB 获取资产行
            a = sess.query(Asset).filter(Asset.id == asset.id).first()
            if not a:
                return None
            # 解析连接配置
            config = {}
            try:
                raw = a.connection_config
                if isinstance(raw, str):
                    config = json.loads(raw) if raw else {}
                else:
                    config = raw or {}
            except (json.JSONDecodeError, TypeError):
                config = {}

            result = ConnectionTester.test(a.connection_type or "ssh", a.ip, config)
            old_status = a.status
            new_status = "online" if result.get("ok") else "offline"
            a.status = new_status
            a.last_checked = datetime.now()
            a.latency_ms = int(result.get("latency_ms", 0)) if result.get("ok") else None
            sess.commit()

            if old_status != new_status:
                return {"id": a.id, "name": a.name,
                        "old": old_status, "new": new_status,
                        "message": result.get("message", "")}
            return None
        except Exception as e:
            sess.rollback()
            from app.logger import logger
            logger.warning(f"probe {asset.name}({asset.ip}) 探测异常: {e}")
            return None
        finally:
            sess.close()

    # 限制并发数 10，避免同时开太多 SSH 连接
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_probe_one, a): a for a in assets}
        for future in as_completed(futures):
            c = future.result()
            if c:
                changed.append(c)
                with _lock:
                    logger.info(f"probe {c['name']}({futures[future].ip}): {c['old']} -> {c['new']} ({c['message']})")

    return changed
