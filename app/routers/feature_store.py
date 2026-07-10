import json
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Body
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import FeatureStoreItem, Asset

router = APIRouter(prefix="/feature-store", tags=["feature-store"])


@router.get("/api/list")
def api_feature_list(db: Session = Depends(get_db), page: int = 1, page_size: int = 20):
    features = [f[0] for f in db.query(FeatureStoreItem.feature_name).distinct().order_by(FeatureStoreItem.feature_name).all()]
    entities = [e[0] for e in db.query(FeatureStoreItem.entity_type).distinct().all()]
    query = db.query(FeatureStoreItem).order_by(desc(FeatureStoreItem.created_at))
    total = query.count()
    recent = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "features": features, "entities": entities,
        "total": total,
        "page": page,
        "page_size": page_size,
        "recent": [
            {
                "id": r.id, "feature_name": r.feature_name, "entity_type": r.entity_type,
                "entity_id": r.entity_id, "feature_value": r.feature_value,
                "feature_json": r.feature_json, "source": r.source,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent
        ],
    }


@router.post("/api/add")
def api_feature_add(payload: dict = Body(...), db: Session = Depends(get_db)):
    item = FeatureStoreItem(
        feature_name=payload.get("feature_name", ""),
        entity_type=payload.get("entity_type", "asset"),
        entity_id=int(payload.get("entity_id", 0) or 0),
        feature_value=float(payload.get("feature_value", 0.0) or 0.0),
        feature_json=payload.get("feature_json", "{}") or "{}",
        source=payload.get("source", "manual"))
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"status": "ok", "id": item.id}


@router.post("/api/query")
def api_feature_query(payload: dict = Body(...), db: Session = Depends(get_db)):
    q = db.query(FeatureStoreItem)
    fn = payload.get("feature_name", "")
    et = payload.get("entity_type", "")
    eid = int(payload.get("entity_id", 0) or 0)
    if fn:
        q = q.filter(FeatureStoreItem.feature_name == fn)
    if et:
        q = q.filter(FeatureStoreItem.entity_type == et)
    if eid > 0:
        q = q.filter(FeatureStoreItem.entity_id == eid)
    items = q.order_by(desc(FeatureStoreItem.created_at)).limit(100).all()
    return {
        "items": [
            {
                "id": it.id, "feature_name": it.feature_name, "entity_type": it.entity_type,
                "entity_id": it.entity_id, "feature_value": it.feature_value,
                "feature_json": it.feature_json, "source": it.source,
                "created_at": it.created_at.isoformat() if it.created_at else None,
            }
            for it in items
        ],
        "count": len(items),
    }
