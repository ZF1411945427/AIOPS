from datetime import datetime
from fastapi import APIRouter, Depends, Body, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import TraceAnomalyConfig

router = APIRouter(prefix="/trace-anomaly", tags=["trace-anomaly"])


def _cfg_to_dict(c):
    return {
        "id": c.id,
        "name": c.name or "",
        "service_name": c.service_name or "",
        "latency_threshold_ms": c.latency_threshold_ms or 1000,
        "error_rate_threshold": c.error_rate_threshold or 0.05,
        "check_window_minutes": c.check_window_minutes or 30,
        "enabled": bool(c.enabled),
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else None,
    }


@router.get("/api/configs")
def list_configs(service_name: str = "", enabled: bool = None, db: Session = Depends(get_db)):
    q = db.query(TraceAnomalyConfig)
    if service_name:
        q = q.filter(TraceAnomalyConfig.service_name.ilike(f"%{service_name}%"))
    if enabled is not None:
        q = q.filter(TraceAnomalyConfig.enabled == enabled)
    items = q.order_by(TraceAnomalyConfig.created_at.desc()).all()
    return JSONResponse({"items": [_cfg_to_dict(c) for c in items], "total": len(items)})


@router.get("/api/configs/{config_id}")
def get_config(config_id: int, db: Session = Depends(get_db)):
    c = db.query(TraceAnomalyConfig).filter(TraceAnomalyConfig.id == config_id).first()
    if not c:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(_cfg_to_dict(c))


@router.post("/api/configs")
def create_config(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        cfg = TraceAnomalyConfig(
            name=payload.get("name", ""),
            service_name=payload.get("service_name", ""),
            latency_threshold_ms=payload.get("latency_threshold_ms", 1000),
            error_rate_threshold=payload.get("error_rate_threshold", 0.05),
            check_window_minutes=payload.get("check_window_minutes", 30),
            enabled=payload.get("enabled", True),
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
        return JSONResponse({"ok": True, "id": cfg.id, "item": _cfg_to_dict(cfg)})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.put("/api/configs/{config_id}")
def update_config(config_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        cfg = db.query(TraceAnomalyConfig).filter(TraceAnomalyConfig.id == config_id).first()
        if not cfg:
            return JSONResponse({"error": "not found"}, status_code=404)
        if "name" in payload:
            cfg.name = payload["name"]
        if "service_name" in payload:
            cfg.service_name = payload["service_name"]
        if "latency_threshold_ms" in payload:
            cfg.latency_threshold_ms = payload["latency_threshold_ms"]
        if "error_rate_threshold" in payload:
            cfg.error_rate_threshold = payload["error_rate_threshold"]
        if "check_window_minutes" in payload:
            cfg.check_window_minutes = payload["check_window_minutes"]
        if "enabled" in payload:
            cfg.enabled = payload["enabled"]
        db.commit()
        db.refresh(cfg)
        return JSONResponse({"ok": True, "item": _cfg_to_dict(cfg)})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.delete("/api/configs/{config_id}")
def delete_config(config_id: int, db: Session = Depends(get_db)):
    try:
        cfg = db.query(TraceAnomalyConfig).filter(TraceAnomalyConfig.id == config_id).first()
        if not cfg:
            return JSONResponse({"error": "not found"}, status_code=404)
        db.delete(cfg)
        db.commit()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/configs/{config_id}/toggle")
def toggle_config(config_id: int, db: Session = Depends(get_db)):
    try:
        cfg = db.query(TraceAnomalyConfig).filter(TraceAnomalyConfig.id == config_id).first()
        if not cfg:
            return JSONResponse({"error": "not found"}, status_code=404)
        cfg.enabled = not cfg.enabled
        db.commit()
        return JSONResponse({"ok": True, "enabled": bool(cfg.enabled)})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)
