from sqlalchemy.orm import Session

from app.models import Asset
from app.database import get_session_for, get_db_mode


def list_assets(db: Session, search: str = "", type: str = "", ci_type: str = ""):
    q = db.query(Asset)
    if search:
        q = q.filter(Asset.name.ilike(f"%{search}%"))
    if type:
        q = q.filter(Asset.ci_type == type)
    if ci_type:
        types = [t.strip() for t in ci_type.split(",") if t.strip()]
        if len(types) == 1:
            q = q.filter(Asset.ci_type == types[0])
        elif types:
            q = q.filter(Asset.ci_type.in_(types))
    return q.order_by(Asset.id.desc()).all()


def list_assets_paged(db: Session, search: str = "", type: str = "", ci_type: str = "", page: int = 1, page_size: int = 20, exclude_types: set = None):
    q = db.query(Asset)
    if search:
        q = q.filter(Asset.name.ilike(f"%{search}%"))
    if type:
        q = q.filter(Asset.ci_type == type)
    if ci_type:
        types = [t.strip() for t in ci_type.split(",") if t.strip()]
        if len(types) == 1:
            q = q.filter(Asset.ci_type == types[0])
        elif types:
            q = q.filter(Asset.ci_type.in_(types))
    if exclude_types:
        q = q.filter(Asset.ci_type.notin_(exclude_types))
    total = q.count()
    assets = q.order_by(Asset.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return assets, total


def list_by_ci_type(db: Session, ci_type: str):
    return db.query(Asset).filter(Asset.ci_type == ci_type).order_by(Asset.name).all()


def get_asset(db: Session, asset_id: int):
    return db.query(Asset).filter(Asset.id == asset_id).first()


def create_asset(db: Session, data: dict):
    from sqlalchemy import text
    max_id = db.execute(text("SELECT COALESCE(MAX(id), 0) FROM assets")).scalar() or 0
    data["id"] = max_id + 1
    asset = Asset(**data)
    db.add(asset)
    db.commit()
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
    """批量探测所有资产的连接状态，更新 status / last_checked_at / latency_ms"""
    from app.services.connection_service import ConnectionTester
    from app.logger import logger
    from datetime import datetime
    import json
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    import socket

    assets = db.query(Asset).all()
    changed = []

    _probe_db_factory = lambda: get_session_for(get_db_mode())()
    _lock = threading.Lock()

    def _probe_middleware_port(ip, port, timeout=5):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            t0 = datetime.now()
            s.connect((ip, int(port)))
            lat = int((datetime.now() - t0).total_seconds() * 1000)
            s.close()
            return {"ok": True, "message": f"端口 {port} 连通", "latency_ms": lat}
        except Exception as e:
            return {"ok": False, "message": f"端口 {port} 不通: {e}"}

    def _probe_one(asset):
        if not asset.ip:
            return None
        sess = _probe_db_factory()
        try:
            a = sess.query(Asset).filter(Asset.id == asset.id).first()
            if not a:
                return None
            config = {}
            try:
                raw = a.connection_config
                if isinstance(raw, str):
                    config = json.loads(raw) if raw else {}
                else:
                    config = raw or {}
            except (json.JSONDecodeError, TypeError):
                config = {}

            ci_attrs = {}
            try:
                raw_attrs = a.ci_attributes
                if isinstance(raw_attrs, str):
                    ci_attrs = json.loads(raw_attrs) if raw_attrs else {}
                else:
                    ci_attrs = raw_attrs or {}
            except (json.JSONDecodeError, TypeError):
                ci_attrs = {}

            # 按 CI 类型选择探活方式：有业务端口的探业务端口，否则按 connection_type
            probe_port = None
            if a.ci_type == "middleware":
                probe_port = ci_attrs.get("mw_port", "")
            elif a.ci_type == "database":
                probe_port = ci_attrs.get("db_port", "")

            if probe_port:
                result = _probe_middleware_port(a.ip, probe_port)
            else:
                result = ConnectionTester.test(a.connection_type or "ssh", a.ip, config)

            old_status = a.status
            new_status = "online" if result.get("ok") else "offline"
            a.status = new_status
            a.last_checked_at = datetime.now()
            a.latency_ms = int(result.get("latency_ms", 0)) if result.get("ok") else None
            sess.commit()

# 每次探测都写入 svc_up 指标（不限于状态变化），确保告警系统总能拿到最新值
            try:
                from app.models import MetricRecord, AssetLifecycle
                lifecycle = sess.query(AssetLifecycle).filter(
                    AssetLifecycle.asset_id == a.id,
                    AssetLifecycle.status.in_(["maintenance", "decommissioned", "retired"])
                ).first()
                if not (lifecycle and new_status == "offline"):
                    svc_up = 1.0 if new_status == "online" else 0.0
                    sess.add(MetricRecord(
                        asset_id=a.id, name="svc_up", value=svc_up,
                        unit="", timestamp=datetime.now()
                    ))
                sess.commit()
            except Exception:
                sess.rollback()

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

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_probe_one, a): a for a in assets}
        for future in as_completed(futures):
            c = future.result()
            if c:
                changed.append(c)
                with _lock:
                    logger.info(f"probe {c['name']}({futures[future].ip}): {c['old']} -> {c['new']} ({c['message']})")

    return changed
