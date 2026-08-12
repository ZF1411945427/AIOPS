import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DataSource
from app.services.k8s_cert_service import inspect_cluster, renew_cluster

router = APIRouter(prefix="/k8s/cert", tags=["k8s_cert"])


@router.get("/api/clusters")
def list_cert_clusters(db: Session = Depends(get_db)):
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    result = []
    for ds in clusters:
        cfg = {}
        if ds.auth_config:
            try:
                cfg = json.loads(ds.auth_config) if isinstance(ds.auth_config, str) else (ds.auth_config or {})
            except Exception:
                cfg = {}
        result.append({
            "id": ds.id,
            "name": ds.name,
            "endpoint": ds.endpoint or "",
            "status": ds.last_status or "unknown",
            "has_ssh_host": bool(cfg.get("ssh_host")),
            "has_api_server": bool(cfg.get("k8s_api_server")),
            "k8s_distro": cfg.get("k8s_distro", "auto"),
        })
    return JSONResponse(result)


@router.post("/api/inspect")
async def inspect_cluster_certs(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    ds = db.query(DataSource).filter(DataSource.id == int(body.get("cluster_id", 0))).first()
    if not ds or ds.type != "kubernetes":
        return JSONResponse({"ok": False, "error": "集群不存在或不是 kubernetes 数据源"})
    try:
        result = inspect_cluster(ds)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"巡检失败: {e}"})


@router.post("/api/renew")
async def renew_cluster_certs(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    ds = db.query(DataSource).filter(DataSource.id == int(body.get("cluster_id", 0))).first()
    if not ds or ds.type != "kubernetes":
        return JSONResponse({"ok": False, "error": "集群不存在或不是 kubernetes 数据源"})
    try:
        result = renew_cluster(ds, force=body.get("force", False))
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"续期失败: {e}"})