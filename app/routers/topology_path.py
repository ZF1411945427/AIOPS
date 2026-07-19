from collections import deque, defaultdict
from fastapi import APIRouter, Depends, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Asset, AssetRelation

router = APIRouter(prefix="/topology", tags=["topology"])


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


@router.post("/api/path/find")
def api_path_find(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        source_id = int(payload.get("source_id", 0) or 0)
        target_id = int(payload.get("target_id", 0) or 0)
        if not source_id or not target_id:
            return JSONResponse({"ok": False, "error": "source_id 和 target_id 必填", "path": [], "nodes": []}, status_code=400)
        if source_id == target_id:
            return JSONResponse({"ok": False, "error": "起止节点相同", "path": [], "nodes": []}, status_code=400)
        relations = db.query(AssetRelation).all()
        rel_list = [(r.parent_id, r.child_id) for r in relations]
        path_ids = bfs_path(rel_list, source_id, target_id)
        if not path_ids:
            return JSONResponse({"ok": False, "error": "未发现连通路径", "path": [], "nodes": []}, status_code=200)
        asset_map = {a.id: a for a in db.query(Asset).all()}
        nodes = []
        for pid in path_ids:
            a = asset_map.get(pid)
            if a:
                nodes.append({
                    "id": a.id,
                    "name": a.name,
                    "type": a.ci_type,
                    "ci_type": getattr(a, "ci_type", None),
                    "status": a.status,
                    "ip": a.ip,
                })
        edges = []
        for i in range(len(path_ids) - 1):
            rel = (
                db.query(AssetRelation)
                .filter(
                    ((AssetRelation.parent_id == path_ids[i]) & (AssetRelation.child_id == path_ids[i + 1])) |
                    ((AssetRelation.parent_id == path_ids[i + 1]) & (AssetRelation.child_id == path_ids[i]))
                )
                .first()
            )
            src_a = asset_map.get(path_ids[i])
            dst_a = asset_map.get(path_ids[i + 1])
            edges.append({
                "source_id": path_ids[i],
                "source_name": src_a.name if src_a else str(path_ids[i]),
                "target_id": path_ids[i + 1],
                "target_name": dst_a.name if dst_a else str(path_ids[i + 1]),
                "relation_type": rel.relation_type if rel else "connected",
            })
        return JSONResponse({
            "ok": True,
            "path": path_ids,
            "nodes": nodes,
            "edges": edges,
            "length": len(path_ids) - 1,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e), "path": [], "nodes": []}, status_code=200)
