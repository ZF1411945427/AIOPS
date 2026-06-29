import json
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.template_utils import get_templates
from app.services import asset_service
from app.services.connection_service import ConnectionTester

router = APIRouter(prefix="/assets", tags=["assets"])
templates = get_templates()


@router.get("/api/list")
def asset_api_list(db: Session = Depends(get_db)):
    assets = asset_service.list_assets(db)
    return JSONResponse([{
        "id": a.id, "name": a.name, "type": a.type, "ci_type": getattr(a, 'ci_type', None),
        "ip": a.ip, "status": a.status,
        "connection_type": getattr(a, 'connection_type', None),
        "last_checked": str(a.last_checked) if getattr(a, 'last_checked', None) else None,
        "latency_ms": getattr(a, 'latency_ms', None),
    } for a in assets])


@router.post("/api/test-connection")
def test_connection(
    connection_type: str = Form("ssh"),
    host: str = Form(""),
    connection_config: str = Form("{}"),
):
    try:
        config = json.loads(connection_config) if connection_config else {}
    except:
        config = {}
    result = ConnectionTester.test(connection_type, host, config)
    return JSONResponse(result)


@router.get("", response_class=HTMLResponse)
def asset_list(request: Request, search: str = "", type: str = "", ci_type: str = "", db: Session = Depends(get_db)):
    assets = asset_service.list_assets(db, search, type, ci_type)
    ci_types = ["server", "vm", "node", "cluster", "namespace", "deployment", "statefulset", "daemonset", "pod", "container", "service", "ingress", "pvc"]
    return templates.TemplateResponse("assets.html", {"request": request, "assets": assets, "search": search, "type_filter": type, "ci_type": ci_type, "ci_types": ci_types})


@router.get("/create", response_class=HTMLResponse)
def asset_create_page(request: Request):
    return templates.TemplateResponse("asset_form.html", {"request": request, "asset": None})


@router.post("/create")
def asset_create(
    request: Request,
    name: str = Form(...),
    ci_type: str = Form("server"),
    ip: str = Form(""),
    status: str = Form("offline"),
    tags: str = Form(""),
    parent_id: int = Form(0),
    k8s_cluster: str = Form(""),
    connection_type: str = Form("ssh"),
    ssh_user: str = Form("root"),
    ssh_password: str = Form(""),
    ssh_port: int = Form(22),
    db: Session = Depends(get_db),
):
    config = {"ssh_user": ssh_user, "ssh_password": ssh_password, "ssh_port": ssh_port}

    # 保存前先探测一次连接，连通则 status=online，避免新建资产永远是 offline
    from app.services.connection_service import ConnectionTester
    probe_status = status
    if ip and connection_type:
        try:
            result = ConnectionTester.test(connection_type, ip, config)
            probe_status = "online" if result.get("ok") else "offline"
        except Exception:
            probe_status = status
    data = {
        "name": name, "type": ci_type, "ci_type": ci_type,
        "ip": ip, "status": probe_status, "tags": tags,
        "connection_type": connection_type,
        "connection_config": json.dumps(config),
    }
    if parent_id:
        data["parent_id"] = parent_id
    if k8s_cluster:
        data["k8s_cluster"] = k8s_cluster
    asset_service.create_asset(db, data)
    return RedirectResponse("/assets", status_code=303)


@router.get("/{asset_id}/edit", response_class=HTMLResponse)
def asset_edit_page(request: Request, asset_id: int, db: Session = Depends(get_db)):
    asset = asset_service.get_asset(db, asset_id)
    return templates.TemplateResponse("asset_form.html", {"request": request, "asset": asset})


@router.post("/{asset_id}/edit")
def asset_edit(
    asset_id: int,
    name: str = Form(...),
    ci_type: str = Form("server"),
    ip: str = Form(""),
    status: str = Form("offline"),
    tags: str = Form(""),
    parent_id: int = Form(0),
    k8s_cluster: str = Form(""),
    ci_attributes: str = Form("{}"),
    connection_type: str = Form("ssh"),
    ssh_user: str = Form("root"),
    ssh_password: str = Form(""),
    ssh_port: int = Form(22),
    db: Session = Depends(get_db),
):
    config = {"ssh_user": ssh_user, "ssh_password": ssh_password, "ssh_port": ssh_port}

    # 保存前先探测一次连接，连通则 status=online
    from app.services.connection_service import ConnectionTester
    probe_status = status
    if ip and connection_type:
        try:
            result = ConnectionTester.test(connection_type, ip, config)
            probe_status = "online" if result.get("ok") else "offline"
        except Exception:
            probe_status = status
    data = {
        "name": name, "type": ci_type, "ci_type": ci_type,
        "ip": ip, "status": probe_status, "tags": tags,
        "ci_attributes": ci_attributes,
        "connection_type": connection_type,
        "connection_config": json.dumps(config),
    }
    if parent_id:
        data["parent_id"] = parent_id
    if k8s_cluster:
        data["k8s_cluster"] = k8s_cluster
    asset_service.update_asset(db, asset_id, data)
    return RedirectResponse("/assets", status_code=303)


@router.post("/{asset_id}/delete")
def asset_delete(asset_id: int, db: Session = Depends(get_db)):
    asset_service.delete_asset(db, asset_id)
    return RedirectResponse("/assets", status_code=303)
