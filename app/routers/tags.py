from fastapi import APIRouter, Depends, Request, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Asset

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("/api/cloud")
def api_tag_cloud(db: Session = Depends(get_db)):
    all_assets = db.query(Asset).all()
    tag_map = {}
    for a in all_assets:
        tags = [t.strip() for t in (a.tags or "").split(",") if t.strip()]
        for t in tags:
            tag_map[t] = tag_map.get(t, 0) + 1
    return {"tags": [{"name": k, "count": v} for k, v in sorted(tag_map.items(), key=lambda x: -x[1])]}


@router.get("/api/assets")
def api_tagged_assets(tag: str = "", db: Session = Depends(get_db)):
    all_assets = db.query(Asset).all()
    result = []
    for a in all_assets:
        tags = [t.strip() for t in (a.tags or "").split(",") if t.strip()]
        if tag and tag not in tags:
            continue
        result.append({
            "id": a.id, "name": a.name, "ip": a.ip, "ci_type": a.ci_type, "tags": tags,
        })
    return {"assets": result, "count": len(result)}


@router.get("/api/all-assets")
def api_all_assets(db: Session = Depends(get_db)):
    assets = db.query(Asset).order_by(Asset.name).all()
    return {"assets": [{"id": a.id, "name": a.name, "ip": a.ip, "tags": a.tags or ""} for a in assets]}


@router.post("/api/assign")
def api_tag_assign(payload: dict = Body(...), db: Session = Depends(get_db)):
    asset_id = int(payload.get("asset_id", 0) or 0)
    tag = payload.get("tag", "").strip()
    if not tag or asset_id <= 0:
        return {"status": "error", "message": "参数错误"}
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if asset:
        existing = [t.strip() for t in (asset.tags or "").split(",") if t.strip()]
        if tag not in existing:
            existing.append(tag)
            asset.tags = ",".join(existing)
            db.commit()
    return {"status": "ok"}


@router.post("/api/remove")
def api_tag_remove(payload: dict = Body(...), db: Session = Depends(get_db)):
    asset_id = int(payload.get("asset_id", 0) or 0)
    tag = payload.get("tag", "").strip()
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if asset:
        existing = [t.strip() for t in (asset.tags or "").split(",") if t.strip()]
        existing = [t for t in existing if t != tag]
        asset.tags = ",".join(existing)
        db.commit()
    return {"status": "ok"}
