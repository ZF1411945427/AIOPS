from collections import deque, defaultdict
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Asset, AssetRelation
from app.template_utils import get_templates

router = APIRouter(prefix="/topology", tags=["topology"])
templates = get_templates()


def bfs_path(relations: list[tuple[int, int]], start: int, end: int) -> list[int] | None:
    adj = defaultdict(list)
    for src, dst in relations:
        adj[src].append(dst)
        adj[dst].append(src)
    visited = {start}
    q = deque([[start]])
    while q:
        path = q.popleft()
        node = path[-1]
        if node == end:
            return path
        for nb in adj.get(node, []):
            if nb not in visited:
                visited.add(nb)
                q.append(path + [nb])
    return None


@router.get("/path", response_class=HTMLResponse)
def path_find_page(request: Request, db: Session = Depends(get_db)):
    assets = db.query(Asset).order_by(Asset.name).all()
    return templates.TemplateResponse("topology_path.html", {
        "request": request, "assets": assets, "path_result": None,
    })


@router.post("/path/find", response_class=HTMLResponse)
def path_find(
    request: Request,
    source_id: int = Form(...),
    target_id: int = Form(...),
    db: Session = Depends(get_db),
):
    assets = db.query(Asset).order_by(Asset.name).all()
    if source_id == target_id:
        return templates.TemplateResponse("topology_path.html", {
            "request": request, "assets": assets, "error": "起止节点相同",
        })
    relations = db.query(AssetRelation).all()
    rel_list = [(r.source_id, r.target_id) for r in relations]
    path_ids = bfs_path(rel_list, source_id, target_id)

    if not path_ids:
        return templates.TemplateResponse("topology_path.html", {
            "request": request, "assets": assets, "error": "未发现连通路径",
        })

    asset_map = {a.id: a for a in db.query(Asset).all()}
    path_assets = []
    for pid in path_ids:
        a = asset_map.get(pid)
        if a:
            path_assets.append(a)

    # Also get edges along the path
    path_edges = []
    for i in range(len(path_ids) - 1):
        rel = (
            db.query(AssetRelation)
            .filter(
                ((AssetRelation.source_id == path_ids[i]) & (AssetRelation.target_id == path_ids[i + 1])) |
                ((AssetRelation.source_id == path_ids[i + 1]) & (AssetRelation.target_id == path_ids[i]))
            )
            .first()
        )
        path_edges.append({
            "source_id": path_ids[i],
            "source_name": asset_map.get(path_ids[i], None).name if asset_map.get(path_ids[i]) else str(path_ids[i]),
            "target_id": path_ids[i + 1],
            "target_name": asset_map.get(path_ids[i + 1], None).name if asset_map.get(path_ids[i + 1]) else str(path_ids[i + 1]),
            "relation": rel.relation if rel else "connected",
        })

    return templates.TemplateResponse("topology_path.html", {
        "request": request, "assets": assets,
        "path_result": {"assets": path_assets, "edges": path_edges, "length": len(path_ids) - 1},
    })
