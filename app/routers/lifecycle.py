from datetime import datetime
from fastapi import APIRouter, Depends, Request, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Asset, AssetLifecycle, User

router = APIRouter(prefix="/lifecycle", tags=["lifecycle"])

LIFECYCLE_STATES = ["provisioning", "active", "maintenance", "retired"]
ALLOWED_TRANSITIONS = {
    "provisioning": ["active"],
    "active": ["maintenance", "retired"],
    "maintenance": ["active", "retired"],
    "retired": [],
}


@router.get("/api/list")
def api_lifecycle_list(db: Session = Depends(get_db)):
    try:
        assets = db.query(Asset).order_by(Asset.name).all()
        lifecycles = {}
        for lc in db.query(AssetLifecycle).order_by(AssetLifecycle.created_at.desc()).all():
            if lc.asset_id not in lifecycles:
                lifecycles[lc.asset_id] = lc
        users = {u.id: u.username for u in db.query(User).all()}
        items = []
        for a in assets:
            lc = lifecycles.get(a.id)
            cur_status = lc.status if lc else "provisioning"
            items.append({
                "id": a.id,
                "name": a.name,
                "type": a.type,
                "ci_type": getattr(a, "ci_type", None),
                "ip": a.ip,
                "status": a.status,
                "lifecycle_status": cur_status,
                "previous_status": lc.previous_status if lc else "",
                "lifecycle_changed_at": lc.created_at.strftime("%Y-%m-%d %H:%M:%S") if lc and lc.created_at else None,
                "changed_by": users.get(lc.changed_by) if lc else None,
                "comment": lc.comment if lc else "",
                "allowed_transitions": ALLOWED_TRANSITIONS.get(cur_status, []),
            })
        return JSONResponse({"items": items, "error": None})
    except Exception as e:
        return JSONResponse({"items": [], "error": str(e)}, status_code=500)


@router.get("/api/history/{asset_id}")
def api_lifecycle_history(asset_id: int, db: Session = Depends(get_db)):
    try:
        logs = db.query(AssetLifecycle).filter(
            AssetLifecycle.asset_id == asset_id
        ).order_by(AssetLifecycle.created_at.desc()).all()
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        users = {u.id: u.username for u in db.query(User).all()}
        items = [{
            "id": lc.id,
            "asset_id": lc.asset_id,
            "status": lc.status,
            "previous_status": lc.previous_status,
            "changed_by": users.get(lc.changed_by),
            "changed_by_id": lc.changed_by,
            "comment": lc.comment or "",
            "created_at": lc.created_at.strftime("%Y-%m-%d %H:%M:%S") if lc.created_at else None,
        } for lc in logs]
        return JSONResponse({
            "items": items,
            "asset": {
                "id": asset.id, "name": asset.name, "type": asset.type,
                "ci_type": getattr(asset, "ci_type", None), "status": asset.status, "ip": asset.ip,
            } if asset else None,
            "error": None,
        })
    except Exception as e:
        return JSONResponse({"items": [], "asset": None, "error": str(e)}, status_code=500)


@router.post("/api/transition/{asset_id}")
def api_lifecycle_transition(
    asset_id: int,
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db)):
    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            return JSONResponse({"ok": False, "error": "资产不存在"}, status_code=404)
        to_status = payload.get("to_status", "")
        comment = payload.get("comment", "")
        current_lc = db.query(AssetLifecycle).filter(
            AssetLifecycle.asset_id == asset_id
        ).order_by(AssetLifecycle.created_at.desc()).first()
        prev = current_lc.status if current_lc else "provisioning"
        allowed = ALLOWED_TRANSITIONS.get(prev, [])
        if to_status not in allowed and prev != to_status:
            return JSONResponse({
                "ok": False,
                "error": f"不允许的流转: {prev} -> {to_status}",
                "previous_status": prev,
                "allowed": allowed,
            }, status_code=400)
        db.add(AssetLifecycle(
            asset_id=asset_id, status=to_status,
            previous_status=prev,
            changed_by=request.session.get("user_id"),
            comment=comment))
        if to_status == "active":
            asset.status = "online"
        elif to_status == "maintenance":
            asset.status = "warning"
        elif to_status == "retired":
            asset.status = "offline"
        elif to_status == "provisioning":
            asset.status = "offline"
        db.commit()
        return JSONResponse({
            "ok": True,
            "asset_id": asset_id,
            "previous_status": prev,
            "new_status": to_status,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
