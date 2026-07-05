from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from app.template_utils import get_templates

from app.database import get_db
from app.services import incident_service, rca_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/incidents", tags=["incidents"])
templates = get_templates()


def _incident_to_dict(inc, asset_name: str = "") -> dict:
    return {
        "id": inc.id,
        "title": inc.title or "",
        "severity": inc.severity or "warning",
        "status": inc.status or "open",
        "asset_id": inc.asset_id,
        "asset_name": asset_name,
        "alert_count": inc.alert_count or 0,
        "created_at": inc.created_at.strftime("%Y-%m-%d %H:%M:%S") if inc.created_at else None,
        "resolved_at": inc.resolved_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(inc, "resolved_at", None) else None,
    }


def _alert_to_dict(a) -> dict:
    return {
        "id": a.id,
        "metric_name": a.metric_name,
        "actual_value": a.actual_value,
        "threshold": a.threshold,
        "severity": a.severity,
        "status": a.status,
        "message": a.message or "",
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else None,
    }


@router.get("/api/list")
def api_incident_list(status: str = "", db: Session = Depends(get_db)):
    """故障单列表 JSON API."""
    incidents = incident_service.list_incidents(db, status)
    from app.models import Asset
    asset_ids = {inc.asset_id for inc in incidents if inc.asset_id}
    asset_map = {a.id: a.name for a in db.query(Asset).filter(Asset.id.in_(asset_ids)).all()} if asset_ids else {}
    return JSONResponse({
        "incidents": [_incident_to_dict(inc, asset_map.get(inc.asset_id, "")) for inc in incidents],
        "total": len(incidents),
    })


@router.get("/api/{incident_id}")
def api_incident_detail(incident_id: int, db: Session = Depends(get_db)):
    """故障单详情 JSON API."""
    detail = incident_service.get_incident_detail(db, incident_id)
    if not detail:
        return JSONResponse({"error": "not found"}, status_code=404)
    inc = detail["incident"]
    asset = detail["asset"]
    return JSONResponse({
        "incident": _incident_to_dict(inc, asset.name if asset else ""),
        "alerts": [_alert_to_dict(a) for a in detail["alerts"]],
        "asset": {"id": asset.id, "name": asset.name, "ip": asset.ip or ""} if asset else None,
    })


@router.post("/api/{incident_id}/resolve")
def api_resolve_incident(incident_id: int, db: Session = Depends(get_db)):
    """解决故障单 JSON API."""
    inc = incident_service.resolve_incident(db, incident_id)
    if not inc:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"ok": True})


@router.get("/api/{incident_id}/rca")
def api_incident_rca(incident_id: int, db: Session = Depends(get_db)):
    """故障单根因分析 JSON API."""
    detail = incident_service.get_incident_detail(db, incident_id)
    if not detail:
        return JSONResponse({"error": "not found"}, status_code=404)
    analysis = rca_service.analyze_incident(db, incident_id)

    def _safe(obj):
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "__dict__"):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        return str(obj)
    return JSONResponse({"analysis": _safe(analysis)})


# ─── HTML 路由（fallback）───

