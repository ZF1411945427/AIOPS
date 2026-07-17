from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import asset_discovery_service

router = APIRouter(prefix="/assets/api/discovery", tags=["asset_discovery"])


def _result_to_dict(r):
    return {
        "id": r.id,
        "schedule_id": r.schedule_id,
        "ip": r.ip,
        "hostname": r.hostname,
        "port": r.port,
        "status": r.status,
        "asset_id": r.asset_id,
        "os_type": r.os_type,
        "services": r.services,
        "discovered_at": r.discovered_at.strftime("%Y-%m-%d %H:%M:%S") if r.discovered_at else None,
    }


def _schedule_to_dict(s):
    return {
        "id": s.id,
        "name": s.name,
        "protocol": s.protocol,
        "target_range": s.target_range,
        "port": s.port,
        "schedule_cron": s.schedule_cron,
        "enabled": bool(s.enabled),
        "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else None,
    }


@router.get("/schedules")
def list_schedules(enabled: bool = None, db: Session = Depends(get_db)):
    schedules = asset_discovery_service.list_schedules(db, enabled=enabled)
    return JSONResponse({"items": [_schedule_to_dict(s) for s in schedules]})


@router.post("/schedules")
def create_schedule(payload: dict, db: Session = Depends(get_db)):
    data = {k: v for k, v in payload.items() if k not in ("id", "created_at")}
    sch_id = asset_discovery_service.create_schedule(db, data)
    return JSONResponse({"ok": True, "schedule_id": sch_id})


@router.put("/schedules/{schedule_id}")
def update_schedule(schedule_id: int, payload: dict, db: Session = Depends(get_db)):
    data = {k: v for k, v in payload.items() if k not in ("id", "created_at")}
    sch = asset_discovery_service.update_schedule(schedule_id, data, db)
    if not sch:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse({"ok": True})


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    asset_discovery_service.delete_schedule(schedule_id, db)
    return JSONResponse({"ok": True})


@router.post("/run/{schedule_id}")
def run_discovery(schedule_id: int, db: Session = Depends(get_db)):
    result = asset_discovery_service.run_discovery(schedule_id, db)
    return JSONResponse(result)


@router.get("/results")
def get_results(
    schedule_id: int = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    items, total = asset_discovery_service.get_discovery_results(db, schedule_id=schedule_id, page=page, per_page=per_page)
    return JSONResponse({
        "items": [_result_to_dict(r) for r in items],
        "total": total,
        "page": page,
        "per_page": per_page,
    })
