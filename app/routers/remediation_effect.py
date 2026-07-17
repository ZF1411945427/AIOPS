from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import remediation_effect_service

router = APIRouter(prefix="/remediation/api", tags=["remediation_effect"])


def _effect_to_dict(e):
    return {
        "id": e.id,
        "remediation_id": e.remediation_id,
        "log_id": e.log_id,
        "alert_id": e.alert_id,
        "asset_id": e.asset_id,
        "status_before": e.status_before,
        "status_after": e.status_after,
        "effect": e.effect,
        "checked_at": e.checked_at.strftime("%Y-%m-%d %H:%M:%S") if e.checked_at else None,
        "notes": e.description,
        "created_at": e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else None,
    }


@router.get("/effect-stats")
def get_stats(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    stats = remediation_effect_service.get_effect_stats(db, days=days)
    return JSONResponse(stats)


@router.get("/effects")
def get_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items, total = remediation_effect_service.get_effect_history(db, page=page, per_page=per_page)
    return JSONResponse({
        "items": [_effect_to_dict(e) for e in items],
        "total": total,
        "page": page,
        "per_page": per_page,
    })


@router.post("/effects/check/{log_id}")
def check_effect(log_id: int, db: Session = Depends(get_db)):
    result = remediation_effect_service.track_effect(log_id, db)
    if result.get("ok"):
        return JSONResponse({"ok": True, "effect_id": result.get("effect_id"), "effect": result.get("effect"), "notes": result.get("notes")})
    return JSONResponse({"ok": False, "error": result.get("error")}, status_code=400)


@router.get("/effect-recommendations")
def get_recommendations(limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)):
    recs = remediation_effect_service.get_remediation_recommendations(db, limit=limit)
    return JSONResponse({"items": recs})
