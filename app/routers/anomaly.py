from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import JSONResponse
from app.template_utils import get_templates

from app.database import get_db
from app.models import MetricRecord
from app.services import anomaly_service
from sqlalchemy.orm import Session
from sqlalchemy import distinct

router = APIRouter(prefix="/anomaly", tags=["anomaly"])
templates = get_templates()


def _config_to_dict(c) -> dict:
    return {
        "id": c.id,
        "name": c.name or "",
        "metric_name": c.metric_name or "",
        "asset_id": c.asset_id,
        "algorithm": c.algorithm or "sigma",
        "sensitivity": c.sensitivity if c.sensitivity is not None else 3.0,
        "window_size": c.window_size or 20,
        "period": c.period or 12,
        "enabled": bool(c.enabled),
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else None,
    }


@router.get("/api/list")
def api_config_list(db: Session = Depends(get_db)):
    """异常检测配置列表 JSON API."""
    configs = anomaly_service.list_configs(db)
    return JSONResponse({"configs": [_config_to_dict(c) for c in configs], "total": len(configs)})


@router.post("/api/configs/create")
def api_config_create(
    name: str = Form(...),
    metric_name: str = Form(...),
    asset_id: int = Form(0),
    algorithm: str = Form("sigma"),
    sensitivity: float = Form(3.0),
    window_size: int = Form(20),
    period: int = Form(12),
    db: Session = Depends(get_db)):
    """创建异常检测配置 JSON API."""
    cfg = anomaly_service.create_config(db, {
        "name": name, "metric_name": metric_name,
        "asset_id": asset_id if asset_id > 0 else None,
        "algorithm": algorithm,
        "sensitivity": sensitivity, "window_size": window_size,
        "period": period,
        "enabled": True,
    })
    return JSONResponse({"ok": True, "id": cfg.id})


@router.post("/api/configs/{config_id}/toggle")
def api_config_toggle(config_id: int, db: Session = Depends(get_db)):
    """启用/禁用异常检测配置 JSON API."""
    cfg = anomaly_service.toggle_config(db, config_id)
    if not cfg:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"ok": True, "enabled": bool(cfg.enabled)})


@router.post("/api/configs/{config_id}/delete")
def api_config_delete(config_id: int, db: Session = Depends(get_db)):
    """删除异常检测配置 JSON API."""
    anomaly_service.delete_config(db, config_id)
    return JSONResponse({"ok": True})


@router.get("/api/metrics")
def api_metric_list(db: Session = Depends(get_db)):
    """动态获取指标名列表（从 MetricRecord 表去重查询）."""
    names = db.query(distinct(MetricRecord.name)).order_by(MetricRecord.name).all()
    return JSONResponse({"metrics": [n[0] for n in names]})


