import json
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.template_utils import get_templates

from app.database import get_db
from app.services import datasource_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/datasources", tags=["datasources"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def datasource_list(request: Request, db: Session = Depends(get_db)):
    sources = datasource_service.list_sources(db)
    return templates.TemplateResponse("datasources.html", {
        "request": request, "sources": sources,
        "ds_types": datasource_service.DS_TYPES,
        "auth_types": datasource_service.AUTH_TYPES,
    })


@router.post("/create")
def datasource_create(
    name: str = Form(...),
    type: str = Form(...),
    endpoint: str = Form(""),
    auth_type: str = Form("none"),
    auth_config_user: str = Form(""),
    auth_config_password: str = Form(""),
    auth_config_token: str = Form(""),
    ssh_port: int = Form(22),
    ssh_user: str = Form(""),
    ssh_password: str = Form(""),
    k8s_token: str = Form(""),
    k8s_kubeconfig: str = Form(""),
    docker_socket: str = Form(""),
    es_user: str = Form(""),
    es_password: str = Form(""),
    es_api_key: str = Form(""),
    scrape_interval: int = Form(60),
    mapping_config: str = Form("{}"),
    db: Session = Depends(get_db),
):
    if type == "ssh":
        auth_config = {"port": ssh_port, "username": ssh_user, "password": ssh_password}
        auth_type = "password"
    elif type == "kubernetes":
        auth_config = {"token": k8s_token}
        if k8s_kubeconfig:
            try:
                auth_config["kubeconfig"] = json.loads(k8s_kubeconfig)
            except Exception:
                auth_config["kubeconfig_raw"] = k8s_kubeconfig
        auth_type = "bearer" if k8s_token else "none"
    elif type == "docker":
        auth_config = {"socket": docker_socket} if docker_socket else {}
        auth_type = "none"
    elif type == "elasticsearch":
        auth_config = {"username": es_user, "password": es_password}
        if es_api_key:
            auth_config["api_key"] = es_api_key
        auth_type = "basic" if es_user else ("api_key" if es_api_key else "none")
    else:
        auth_config = {}
        if auth_type == "basic":
            auth_config = {"user": auth_config_user, "password": auth_config_password}
        elif auth_type in ("bearer", "api_key"):
            auth_config = {"token": auth_config_token}

    datasource_service.create_source(db, {
        "name": name, "type": type,
        "endpoint": endpoint, "auth_type": auth_type,
        "auth_config": auth_config,
        "scrape_interval": scrape_interval,
        "mapping_config": mapping_config,
        "enabled": True,
    })
    return RedirectResponse("/datasources", status_code=303)


@router.post("/{source_id}/toggle")
def datasource_toggle(source_id: int, db: Session = Depends(get_db)):
    source = datasource_service.get_source(db, source_id)
    if source:
        datasource_service.update_source(db, source_id, {"enabled": not source.enabled})
    return RedirectResponse("/datasources", status_code=303)


@router.post("/{source_id}/test")
def datasource_test(source_id: int, db: Session = Depends(get_db)):
    datasource_service.test_source(db, source_id)
    return RedirectResponse("/datasources", status_code=303)


@router.post("/{source_id}/delete")
def datasource_delete(source_id: int, db: Session = Depends(get_db)):
    datasource_service.delete_source(db, source_id)
    return RedirectResponse("/datasources", status_code=303)


