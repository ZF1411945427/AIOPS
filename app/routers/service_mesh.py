import json
import requests
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ServiceMeshConfig
from app.template_utils import get_templates

router = APIRouter(prefix="/service-mesh", tags=["service-mesh"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def mesh_page(request: Request, db: Session = Depends(get_db)):
    configs = db.query(ServiceMeshConfig).all()
    return templates.TemplateResponse("service_mesh.html", {
        "request": request, "configs": configs, "result": None,
    })


@router.post("/create")
def create_config(
    request: Request, name: str = Form(...), mesh_type: str = Form("istio"),
    api_url: str = Form(""), auth_json: str = Form("{}"),
    db: Session = Depends(get_db),
):
    cfg = ServiceMeshConfig(name=name, mesh_type=mesh_type, api_url=api_url, auth_config=auth_json)
    db.add(cfg)
    db.commit()
    return RedirectResponse("/service-mesh", status_code=303)


@router.post("/toggle/{cid}")
def toggle_config(cid: int, db: Session = Depends(get_db)):
    c = db.query(ServiceMeshConfig).filter(ServiceMeshConfig.id == cid).first()
    if c:
        c.enabled = not c.enabled
        db.commit()
    return RedirectResponse("/service-mesh", status_code=303)


@router.post("/query/{cid}", response_class=HTMLResponse)
def query_mesh(cid: int, request: Request, db: Session = Depends(get_db)):
    cfg = db.query(ServiceMeshConfig).filter(ServiceMeshConfig.id == cid).first()
    if not cfg:
        return PlainTextResponse("Config not found", 404)
    result = None
    try:
        if cfg.mesh_type == "istio":
            base = cfg.api_url or "http://localhost:15090"
            resp = requests.get(f"{base}/metrics", timeout=15)
            lines = resp.text.strip().split("\n")
            metrics = []
            for line in lines[-50:]:
                if line and not line.startswith("#"):
                    metrics.append(line[:200])
            result = {"raw_metrics": metrics, "count": len(metrics)}
        elif cfg.mesh_type == "linkerd":
            base = cfg.api_url or "http://localhost:4191"
            resp = requests.get(f"{base}/metrics", timeout=15)
            lines = resp.text.strip().split("\n")
            metrics = []
            for line in lines[-50:]:
                if line and not line.startswith("#"):
                    metrics.append(line[:200])
            result = {"raw_metrics": metrics, "count": len(metrics)}
    except Exception as e:
        result = {"error": str(e)}
    configs = db.query(ServiceMeshConfig).all()
    return templates.TemplateResponse("service_mesh.html", {
        "request": request, "configs": configs, "result": result,
    })
