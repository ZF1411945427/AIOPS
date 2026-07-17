import json
import requests
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ExtCmdbConfig, Asset
from app.template_utils import parse_json_config

router = APIRouter(prefix="/ext-cmdb", tags=["ext-cmdb"])


@router.get("/api/list")
def api_cmdb_list(db: Session = Depends(get_db)):
    configs = db.query(ExtCmdbConfig).order_by(ExtCmdbConfig.id.desc()).all()
    return {
        "configs": [
            {
                "id": c.id, "name": c.name, "cmdb_type": c.cmdb_type,
                "api_url": c.api_url, "sync_interval": c.sync_interval,
                "last_synced_at": c.last_synced_at.isoformat() if c.last_synced_at else None,
                "enabled": c.enabled,
            }
            for c in configs
        ],
        "count": len(configs),
    }


@router.post("/api/create")
def api_cmdb_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    cfg = ExtCmdbConfig(
        name=payload.get("name", ""), cmdb_type=payload.get("cmdb_type", "generic"),
        api_url=payload.get("api_url", ""),
        auth_config=payload.get("auth_json", "{}") or "{}",
        sync_interval=payload.get("sync_interval", 60))
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return {"status": "ok", "id": cfg.id}


@router.post("/api/{cfg_id}/toggle")
def api_cmdb_toggle(cfg_id: int, db: Session = Depends(get_db)):
    cfg = db.query(ExtCmdbConfig).filter(ExtCmdbConfig.id == cfg_id).first()
    if cfg:
        cfg.enabled = not cfg.enabled
        db.commit()
    return {"status": "ok", "enabled": cfg.enabled if cfg else None}


@router.delete("/api/{cfg_id}/delete")
def api_cmdb_delete(cfg_id: int, db: Session = Depends(get_db)):
    cfg = db.query(ExtCmdbConfig).filter(ExtCmdbConfig.id == cfg_id).first()
    if cfg:
        db.delete(cfg)
        db.commit()
    return {"status": "ok"}


@router.post("/api/{cfg_id}/sync")
def api_cmdb_sync(cfg_id: int, db: Session = Depends(get_db)):
    cfg = db.query(ExtCmdbConfig).filter(ExtCmdbConfig.id == cfg_id).first()
    if not cfg:
        return {"status": "error", "message": "配置不存在"}
    try:
        auth = parse_json_config(cfg.auth_config)
        headers = {}
        token = auth.get("token") or auth.get("api_key", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(cfg.api_url, headers=headers, timeout=30)
        data = resp.json() if resp.ok else []
        count = 0
        if isinstance(data, list):
            for item in data:
                name = item.get("name") or item.get("hostname") or f"cmdb-{count}"
                ip = item.get("ip") or item.get("ip_address") or ""
                ci_type = item.get("ci_type") or item.get("type") or "server"
                tags = item.get("tags", "") or ""
                existing = db.query(Asset).filter(
                    (Asset.name == name) | ((Asset.ip != "") & (Asset.ip == ip))
                ).first()
                if not existing:
                    db.add(Asset(name=name, ip=ip, ci_type=ci_type, type=ci_type, tags=tags))
                    count += 1
        db.commit()
        cfg.last_synced_at = datetime.now()
        db.commit()
        return {"status": "ok", "synced": count}
    except Exception as e:
        return {"status": "error", "message": f"同步失败: {e}"}
