import json
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import FeatureStoreItem, Asset
from app.template_utils import get_templates

router = APIRouter(prefix="/feature-store", tags=["feature-store"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def feature_store_page(request: Request, db: Session = Depends(get_db)):
    features = db.query(FeatureStoreItem.feature_name).distinct().order_by(FeatureStoreItem.feature_name).all()
    entities = db.query(FeatureStoreItem.entity_type).distinct().all()
    recent = db.query(FeatureStoreItem).order_by(desc(FeatureStoreItem.created_at)).limit(50).all()
    return templates.TemplateResponse("feature_store.html", {
        "request": request, "features": features, "entities": entities, "recent": recent, "result": None,
    })


@router.post("/add")
def add_feature(
    request: Request, feature_name: str = Form(...),
    entity_type: str = Form("asset"), entity_id: int = Form(0),
    feature_value: float = Form(0.0), feature_json: str = Form("{}"),
    source: str = Form("manual"), db: Session = Depends(get_db),
):
    item = FeatureStoreItem(
        feature_name=feature_name, entity_type=entity_type, entity_id=entity_id,
        feature_value=feature_value, feature_json=feature_json, source=source,
    )
    db.add(item)
    db.commit()
    return RedirectResponse("/feature-store", status_code=303)


@router.post("/query", response_class=HTMLResponse)
def query_feature(
    request: Request, feature_name: str = Form(""),
    entity_type: str = Form(""), entity_id: int = Form(0),
    db: Session = Depends(get_db),
):
    q = db.query(FeatureStoreItem)
    if feature_name:
        q = q.filter(FeatureStoreItem.feature_name == feature_name)
    if entity_type:
        q = q.filter(FeatureStoreItem.entity_type == entity_type)
    if entity_id > 0:
        q = q.filter(FeatureStoreItem.entity_id == entity_id)
    items = q.order_by(desc(FeatureStoreItem.created_at)).limit(100).all()
    features = db.query(FeatureStoreItem.feature_name).distinct().order_by(FeatureStoreItem.feature_name).all()
    entities = db.query(FeatureStoreItem.entity_type).distinct().all()
    recent = db.query(FeatureStoreItem).order_by(desc(FeatureStoreItem.created_at)).limit(50).all()
    return templates.TemplateResponse("feature_store.html", {
        "request": request, "features": features, "entities": entities,
        "recent": recent, "result": items,
    })
