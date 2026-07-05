from fastapi import APIRouter, Depends, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import topology_service
from app.models import Asset, AssetRelation

router = APIRouter(prefix="/topology", tags=["topology"])


@router.get("/api/list")
def api_topology_list(db: Session = Depends(get_db)):
    try:
        trees = topology_service.build_topo(db)
        assets = db.query(Asset).order_by(Asset.name).all()
        relations = topology_service.get_relations(db)
        nodes = [{
            "id": a.id,
            "name": a.name,
            "type": a.type,
            "ci_type": getattr(a, "ci_type", None),
            "status": a.status,
            "parent_id": getattr(a, "parent_id", None),
            "ip": a.ip,
            "k8s_cluster": getattr(a, "k8s_cluster", None) or "",
        } for a in assets]
        edges = [{
            "id": r.id,
            "source_id": r.parent_id,
            "target_id": r.child_id,
            "relation_type": r.relation_type,
        } for r in relations]
        return JSONResponse({
            "nodes": nodes,
            "edges": edges,
            "relations": edges,
            "trees": trees,
        })
    except Exception as e:
        return JSONResponse({"nodes": [], "edges": [], "relations": [], "trees": [], "error": str(e)}, status_code=500)


@router.post("/api/relations/create")
def api_relation_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        source_id = int(payload.get("source_id", 0) or 0)
        target_id = int(payload.get("target_id", 0) or 0)
        relation_type = payload.get("relation_type", "depends_on") or "depends_on"
        if not source_id or not target_id:
            return JSONResponse({"ok": False, "error": "source_id 和 target_id 必填"}, status_code=400)
        r = topology_service.create_relation(db, source_id, target_id, relation_type)
        if r is None:
            return JSONResponse({"ok": False, "error": "source_id 与 target_id 相同或关系已存在"})
        return JSONResponse({
            "ok": True,
            "id": r.id,
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": relation_type,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/relations/{relation_id}/delete")
def api_relation_delete(relation_id: int, db: Session = Depends(get_db)):
    try:
        topology_service.delete_relation(db, relation_id)
        return JSONResponse({"ok": True, "id": relation_id})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
