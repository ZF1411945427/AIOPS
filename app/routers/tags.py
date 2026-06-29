from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Asset
from app.template_utils import get_templates

router = APIRouter(prefix="/tags", tags=["tags"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def tag_list(request: Request, tag: str = "", db: Session = Depends(get_db)):
    all_assets = db.query(Asset).all()
    tag_map = {}
    for a in all_assets:
        tags = [t.strip() for t in (a.tags or "").split(",") if t.strip()]
        for t in tags:
            if t not in tag_map:
                tag_map[t] = []
            tag_map[t].append(a)
    if tag:
        tagged_assets = tag_map.get(tag, [])
    else:
        tagged_assets = []
    return templates.TemplateResponse("tags.html", {
        "request": request, "tag_map": tag_map, "current_tag": tag, "tagged_assets": tagged_assets,
    })


@router.post("/assign")
def assign_tag(asset_id: int = Form(...), tag: str = Form(...), db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if asset:
        existing = [t.strip() for t in (asset.tags or "").split(",") if t.strip()]
        if tag not in existing:
            existing.append(tag)
            asset.tags = ",".join(existing)
            db.commit()
    return RedirectResponse(f"/tags?tag={tag}", status_code=303)


@router.post("/remove")
def remove_tag(asset_id: int = Form(...), tag: str = Form(...), db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if asset:
        existing = [t.strip() for t in (asset.tags or "").split(",") if t.strip()]
        existing = [t for t in existing if t != tag]
        asset.tags = ",".join(existing)
        db.commit()
    return RedirectResponse(f"/tags?tag={tag}", status_code=303)
