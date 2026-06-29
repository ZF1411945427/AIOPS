from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Asset, AssetLifecycle, User
from app.template_utils import get_templates

router = APIRouter(prefix="/lifecycle", tags=["lifecycle"])
templates = get_templates()

LIFECYCLE_STATES = ["provisioning", "active", "maintenance", "retired"]
ALLOWED_TRANSITIONS = {
    "provisioning": ["active"],
    "active": ["maintenance", "retired"],
    "maintenance": ["active", "retired"],
    "retired": [],
}


@router.get("", response_class=HTMLResponse)
def lifecycle_list(request: Request, db: Session = Depends(get_db)):
    assets = db.query(Asset).order_by(Asset.name).all()
    lifecycles = {}
    for lc in db.query(AssetLifecycle).order_by(AssetLifecycle.created_at.desc()).all():
        if lc.asset_id not in lifecycles:
            lifecycles[lc.asset_id] = lc
    users = {u.id: u.username for u in db.query(User).all()}
    return templates.TemplateResponse("lifecycle.html", {
        "request": request, "assets": assets, "lifecycles": lifecycles,
        "states": LIFECYCLE_STATES, "transitions": ALLOWED_TRANSITIONS,
        "users": users,
    })


@router.post("/transition/{asset_id}")
def lifecycle_transition(
    asset_id: int,
    request: Request,
    new_status: str = Form(...),
    comment: str = Form(""),
    db: Session = Depends(get_db),
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return RedirectResponse("/lifecycle", status_code=303)
    current_lc = db.query(AssetLifecycle).filter(
        AssetLifecycle.asset_id == asset_id
    ).order_by(AssetLifecycle.created_at.desc()).first()
    prev = current_lc.status if current_lc else "provisioning"
    allowed = ALLOWED_TRANSITIONS.get(prev, [])
    if new_status not in allowed and prev != new_status:
        return RedirectResponse("/lifecycle", status_code=303)
    db.add(AssetLifecycle(
        asset_id=asset_id, status=new_status,
        previous_status=prev,
        changed_by=request.session.get("user_id"),
        comment=comment,
    ))
    if new_status == "active":
        asset.status = "online"
    elif new_status == "maintenance":
        asset.status = "warning"
    elif new_status == "retired":
        asset.status = "offline"
    elif new_status == "provisioning":
        asset.status = "offline"
    db.commit()
    return RedirectResponse("/lifecycle", status_code=303)


@router.get("/history/{asset_id}", response_class=HTMLResponse)
def lifecycle_history(asset_id: int, request: Request, db: Session = Depends(get_db)):
    logs = db.query(AssetLifecycle).filter(
        AssetLifecycle.asset_id == asset_id
    ).order_by(AssetLifecycle.created_at.desc()).all()
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    users = {u.id: u.username for u in db.query(User).all()}
    return templates.TemplateResponse("lifecycle_history.html", {
        "request": request, "logs": logs, "asset": asset, "users": users,
    })
