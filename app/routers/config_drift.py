"""配置漂移检测与 AI 配置推荐 API 路由 (对标天穹「AI 智能化配置」)

端点:
  GET    /config-drift/api/stats            — 漂移统计
  GET    /config-drift/api/templates        — 内置采集模板清单
  GET    /config-drift/api/baselines        — 配置基线列表(?asset_id=)
  POST   /config-drift/api/baselines        — 建立/更新基线 {asset_id, config_key, config_name?, category?, source_command?}
  DELETE /config-drift/api/baselines/{id}   — 删除基线
  GET    /config-drift/api/drifts           — 漂移记录列表(?asset_id=&status=&limit=)
  GET    /config-drift/api/drifts/{id}      — 漂移详情
  POST   /config-drift/api/drifts/{id}/assess — AI 评估漂移
  POST   /config-drift/api/drifts/{id}/status — 更新漂移状态
  POST   /config-drift/api/detect           — 对资产+配置项执行漂移检测
"""
from fastapi import APIRouter, Query, Body

from app.database import get_db
from app.services.config_drift_service import (
    list_builtin_templates, list_baselines, capture_baseline, delete_baseline,
    list_drifts, get_drift, detect_drift, ai_assess, set_drift_status, get_drift_stats,
)

router = APIRouter(prefix="/config-drift", tags=["ConfigDrift"])


@router.get("/api/stats")
def api_stats():
    db = next(get_db())
    return get_drift_stats(db)


@router.get("/api/templates")
def api_templates():
    db = next(get_db())
    return {"items": list_builtin_templates(db)}


@router.get("/api/baselines")
def api_baselines(asset_id: int = Query(None)):
    db = next(get_db())
    return {"items": list_baselines(db, asset_id=asset_id)}


@router.post("/api/baselines")
def api_create_baseline(body: dict = Body(...)):
    db = next(get_db())
    try:
        item = capture_baseline(
            db,
            asset_id=body.get("asset_id"),
            config_key=body.get("config_key", ""),
            config_name=body.get("config_name", ""),
            category=body.get("category", "custom"),
            source_command=body.get("source_command", ""),
        )
        return {"ok": True, "item": item}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@router.delete("/api/baselines/{baseline_id}")
def api_delete_baseline(baseline_id: int):
    db = next(get_db())
    if delete_baseline(db, baseline_id):
        return {"ok": True}
    return {"ok": False, "error": "基线不存在"}


@router.get("/api/drifts")
def api_drifts(asset_id: int = Query(None), status: str = Query(None), limit: int = Query(100)):
    db = next(get_db())
    return {"items": list_drifts(db, asset_id=asset_id, status=status, limit=limit)}


@router.get("/api/drifts/{drift_id}")
def api_drift_detail(drift_id: int):
    db = next(get_db())
    item = get_drift(db, drift_id)
    if not item:
        return {"ok": False, "error": "漂移记录不存在"}
    return {"ok": True, "item": item}


@router.post("/api/drifts/{drift_id}/assess")
def api_assess(drift_id: int):
    db = next(get_db())
    try:
        return {"ok": True, "assessment": ai_assess(db, drift_id)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/drifts/{drift_id}/status")
def api_status(drift_id: int, body: dict = Body(...)):
    db = next(get_db())
    status = body.get("status", "")
    item = set_drift_status(db, drift_id, status)
    if not item:
        return {"ok": False, "error": "漂移记录不存在"}
    return {"ok": True, "item": item}


@router.post("/api/detect")
def api_detect(body: dict = Body(...)):
    db = next(get_db())
    try:
        result = detect_drift(
            db,
            asset_id=body.get("asset_id"),
            config_key=body.get("config_key", ""),
            config_name=body.get("config_name", ""),
            category=body.get("category", "custom"),
            source_command=body.get("source_command", ""),
        )
        return {"ok": True, "result": result}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
