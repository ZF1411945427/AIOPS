import json
import requests
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ExtCmdbConfig, Asset
from app.template_utils import get_templates

router = APIRouter(prefix="/ext-cmdb", tags=["ext-cmdb"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def ext_cmdb_page(request: Request, db: Session = Depends(get_db)):
    configs = db.query(ExtCmdbConfig).all()
    return templates.TemplateResponse("ext_cmdb.html", {
        "request": request, "configs": configs,
    })


@router.post("/create")
def create_config(
    request: Request, name: str = Form(...), cmdb_type: str = Form("generic"),
    api_url: str = Form(...), auth_json: str = Form("{}"),
    sync_interval: int = Form(60), db: Session = Depends(get_db),
):
    cfg = ExtCmdbConfig(name=name, cmdb_type=cmdb_type, api_url=api_url,
                         auth_config=auth_json, sync_interval=sync_interval)
    db.add(cfg)
    db.commit()
    return RedirectResponse("/ext-cmdb", status_code=303)


@router.post("/toggle/{cfg_id}")
def toggle_config(cfg_id: int, db: Session = Depends(get_db)):
    cfg = db.query(ExtCmdbConfig).filter(ExtCmdbConfig.id == cfg_id).first()
    if cfg:
        cfg.enabled = not cfg.enabled
        db.commit()
    return RedirectResponse("/ext-cmdb", status_code=303)


@router.post("/sync/{cfg_id}")
def sync_cmdb(cfg_id: int, db: Session = Depends(get_db)):
    cfg = db.query(ExtCmdbConfig).filter(ExtCmdbConfig.id == cfg_id).first()
    if not cfg:
        return PlainTextResponse("Config not found", 404)
    try:
        auth = json.loads(cfg.auth_config) if isinstance(cfg.auth_config, str) else cfg.auth_config or {}
        headers = {}
        token = auth.get("token") or auth.get("api_key", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(cfg.api_url, headers=headers, timeout=30)
        data = resp.json() if resp.ok else []
        count = 0
        if isinstance(data, list):
            for item in data:
                name = item.get("name") or item.get("hostname") or f"cmdb-{count}"
                ip = item.get("ip") or item.get("ip_address") or ""
                ci_type = item.get("ci_type") or item.get("type") or "server"
                tags = item.get("tags", "") or ""
                existing = db.query(Asset).filter(
                    (Asset.name == name) | ((Asset.ip != "") & (Asset.ip == ip))
                ).first()
                if not existing:
                    db.add(Asset(name=name, ip=ip, ci_type=ci_type, type=ci_type, tags=tags))
                    count += 1
        db.commit()
        cfg.last_sync = datetime.now()
        db.commit()
        return PlainTextResponse(f"Synced {count} new assets", 200)
    except Exception as e:
        return PlainTextResponse(f"Sync error: {e}", 500)
