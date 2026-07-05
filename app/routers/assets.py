import json
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.template_utils import get_templates
from app.services import asset_service
from app.services.connection_service import ConnectionTester

router = APIRouter(prefix="/assets", tags=["assets"])
templates = get_templates()


@router.get("/api/list")
def asset_api_list(search: str = "", ci_type: str = "", db: Session = Depends(get_db)):
    assets = asset_service.list_assets(db, search, "", ci_type)
    return JSONResponse([{
        "id": a.id, "name": a.name, "type": a.type, "ci_type": getattr(a, 'ci_type', None),
        "ip": a.ip, "status": a.status,
        "connection_type": getattr(a, 'connection_type', None),
        "last_checked": a.last_checked.strftime("%Y-%m-%d %H:%M:%S") if getattr(a, 'last_checked', None) else None,
        "latency_ms": getattr(a, 'latency_ms', None),
        "k8s_cluster": getattr(a, 'k8s_cluster', None) or "",
        "tags": getattr(a, 'tags', None) or "",
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if getattr(a, 'created_at', None) else None,
    } for a in assets])


@router.get("/api/ci-types")
def asset_api_ci_types(db: Session = Depends(get_db)):
    """返回可用 CI 类型列表."""
    ci_types = ["server", "vm", "node", "cluster", "namespace", "deployment", "statefulset", "daemonset", "pod", "container", "service", "ingress", "pvc"]
    return JSONResponse(ci_types)


@router.post("/api/{asset_id}/delete")
def api_asset_delete(asset_id: int, db: Session = Depends(get_db)):
    asset_service.delete_asset(db, asset_id)
    return JSONResponse({"ok": True})


@router.post("/api/test-connection")
def test_connection(
    connection_type: str = Form("ssh"),
    host: str = Form(""),
    connection_config: str = Form("{}")):
    try:
        config = json.loads(connection_config) if connection_config else {}
    except:
        config = {}
    result = ConnectionTester.test(connection_type, host, config)
    return JSONResponse(result)


