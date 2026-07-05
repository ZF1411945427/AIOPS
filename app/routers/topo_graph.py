from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Asset, AssetRelation, Alert
from app.template_utils import get_templates

router = APIRouter(prefix="/topo-graph", tags=["topo_graph"])
templates = get_templates()


@router.get("/data")
def topo_graph_data(db: Session = Depends(get_db)):
    assets = db.query(Asset).all()
    relations = db.query(AssetRelation).all()
    alerts = db.query(Alert).filter(Alert.status == "triggered").all()
    alert_asset_ids = {a.asset_id for a in alerts if a.asset_id}

    nodes = []
    for a in assets:
        ci = a.ci_type or a.type or "unknown"
        color = "#ef4444" if a.id in alert_asset_ids else "#3b82f6"
        if ci == "cluster": color = "#8b5cf6"
        elif ci == "namespace": color = "#06b6d4"
        elif ci == "deployment": color = "#10b981"
        elif ci == "pod": color = "#f59e0b"
        elif ci == "service": color = "#ec4899"
        nodes.append({"id": a.id, "name": a.name, "type": ci, "color": color, "status": a.status})

    links = []
    for r in relations:
        links.append({"source": r.source_id, "target": r.target_id, "type": r.relation_type or "depends"})

    return JSONResponse({"nodes": nodes, "links": links})
