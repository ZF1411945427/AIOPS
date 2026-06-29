from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Asset, AssetRelation
from app.services import topology_service
from app.template_utils import get_templates

router = APIRouter(prefix="/trace-view", tags=["trace_view"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def trace_view(request: Request, root_id: int = 0, db: Session = Depends(get_db)):
    assets = db.query(Asset).order_by(Asset.name).all()
    graph = {"nodes": [], "edges": []}
    if root_id:
        root = db.query(Asset).filter(Asset.id == root_id).first()
        if root:
            seen = {root_id}
            graph["nodes"].append({"id": f"asset_{root.id}", "label": root.name.split("/")[-1], "type": root.ci_type})
            queue = [root]
            depth = 0
            while queue and depth < 4:
                current = queue.pop(0)
                children = db.query(Asset).filter(Asset.parent_id == current.id).all()
                for child in children:
                    if child.id not in seen:
                        seen.add(child.id)
                        graph["nodes"].append({"id": f"asset_{child.id}", "label": child.name.split("/")[-1], "type": child.ci_type})
                        graph["edges"].append({"source": f"asset_{current.id}", "target": f"asset_{child.id}", "relation": "contains"})
                        queue.append(child)
                depth += 1
            relations = db.query(AssetRelation).filter(
                (AssetRelation.parent_id == root_id) | (AssetRelation.child_id == root_id)
            ).all()
            for rel in relations:
                pid = rel.parent_id
                cid = rel.child_id
                if pid not in seen or cid not in seen:
                    target = pid if pid != root_id else cid
                    target_asset = db.query(Asset).filter(Asset.id == target).first()
                    if target_asset and target not in seen:
                        seen.add(target)
                        graph["nodes"].append({"id": f"asset_{target}", "label": target_asset.name.split("/")[-1], "type": target_asset.ci_type})
                        graph["edges"].append({"source": f"asset_{root_id}", "target": f"asset_{target}", "relation": rel.relation_type})
    return templates.TemplateResponse("trace_view.html", {
        "request": request, "assets": assets, "root_id": root_id, "graph": graph,
    })
