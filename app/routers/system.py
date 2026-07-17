from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta

from app.database import get_db

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/overview")
def system_overview(db: Session = Depends(get_db)):
    from app.models import Asset, Alert, Incident, MetricRecord, K8sEvent, DataSource

    total = db.query(func.count(Asset.id)).scalar() or 0
    online = db.query(func.count(Asset.id)).filter(Asset.status == "online").scalar() or 0
    alerts_triggered = db.query(func.count(Alert.id)).filter(Alert.status == "triggered").scalar() or 0
    alerts_ack = db.query(func.count(Alert.id)).filter(Alert.status == "acknowledged").scalar() or 0
    incidents_open = db.query(func.count(Incident.id)).filter(Incident.status == "open").scalar() or 0
    ds_count = db.query(func.count(DataSource.id)).scalar() or 0

    recent1h = datetime.now() - timedelta(hours=1)
    recent24h = datetime.now() - timedelta(hours=24)
    recent_metrics = db.query(func.count(MetricRecord.id)).filter(MetricRecord.timestamp >= recent1h).scalar() or 0
    recent_alerts = db.query(func.count(Alert.id)).filter(Alert.created_at >= recent24h).scalar() or 0

    return JSONResponse({
        "assets": {"total": total, "online": online},
        "alerts": {"triggered": alerts_triggered, "acknowledged": alerts_ack},
        "incidents": {"open": incidents_open},
        "datasources": ds_count,
        "metrics_count_1h": recent_metrics,
        "alerts_count_24h": recent_alerts,
    })

# ── 数据库模式切换 ──
from app.database import get_db_mode, set_db_mode
from pydantic import BaseModel


@router.get("/db-mode")
def get_current_db_mode():
    """获取当前数据库模式"""
    return {"mode": get_db_mode()}


class DBSwitchRequest(BaseModel):
    mode: str  # "demo" or "real"


@router.post("/db-switch")
def switch_db_mode(req: DBSwitchRequest):
    """切换数据库模式 (demo / real)"""
    if req.mode not in ("demo", "real"):
        return JSONResponse({"error": "mode 必须是 demo 或 real"}, status_code=400)
    old_mode = get_db_mode()
    if req.mode == old_mode:
        return {"mode": old_mode, "changed": False, "message": f"已经是 {old_mode} 模式"}
    set_db_mode(req.mode)
    return {
        "mode": req.mode,
        "changed": True,
        "previous": old_mode,
        "message": f"已从 {old_mode} 切换到 {req.mode} 模式",
    }


@router.get("/reload-menu")
def reload_menu(db: Session = Depends(get_db)):
    """手动刷新菜单配置"""
    from app.routers.menu import DEFAULT_MENU
    import json

    cfg = db.query(SystemConfig).filter(SystemConfig.key == "menu_config").first()
    if cfg:
        cfg.config_value = json.dumps(DEFAULT_MENU, ensure_ascii=False)
    else:
        cfg = SystemConfig(key="menu_config", config_value=json.dumps(DEFAULT_MENU, ensure_ascii=False))
        db.add(cfg)
    db.commit()

    return {"status": "ok", "menus": len(DEFAULT_MENU)}


@router.get("/configs")
def get_configs(db: Session = Depends(get_db)):
    """获取所有系统配置"""
    from app.services.config_service import get_all_configs as _get_all_configs
    return _get_all_configs(db)


@router.put("/configs")
def update_configs(configs: dict, db: Session = Depends(get_db)):
    """批量更新系统配置"""
    from app.services.config_service import update_configs as _update_configs
    _update_configs(db, configs)
    return {"ok": True}
