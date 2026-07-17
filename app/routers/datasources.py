import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from app.template_utils import get_templates

from app.database import get_db
from app.services import datasource_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/datasources", tags=["datasources"])
templates = get_templates()


# ─── JSON API（供 Vue 前端调用，保留 HTML 路由作 fallback）───

def _source_to_dict(s):
    return {
        "id": s.id,
        "name": s.name,
        "type": s.type,
        "endpoint": s.endpoint or "",
        "auth_type": s.auth_type or "none",
        "enabled": bool(s.enabled),
        "scrape_interval": getattr(s, "scrape_interval", 60) or 60,
        "last_scraped_at": s.last_scraped_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(s, "last_scraped_at", None) else None,
        "last_status": getattr(s, "last_status", None) or "",
        "created_at": s.created_at.strftime("%Y-%m-%d %H:%M") if getattr(s, "created_at", None) else None,
    }


@router.get("/api/list")
def api_datasource_list(db: Session = Depends(get_db)):
    sources = datasource_service.list_sources(db)
    return JSONResponse({
        "sources": [_source_to_dict(s) for s in sources],
        "ds_types": datasource_service.DS_TYPES,
        "auth_types": datasource_service.AUTH_TYPES,
    })


@router.get("/api/{source_id}")
def api_datasource_get(source_id: int, db: Session = Depends(get_db)):
    source = datasource_service.get_source(db, source_id)
    if not source:
        return JSONResponse({"error": "数据源不存在"}, status_code=404)
    return JSONResponse(_source_to_dict(source))


@router.post("/api/create")
async def api_datasource_create(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    if not body.get("name") or not body.get("type"):
        return JSONResponse({"error": "name 和 type 为必填项"}, status_code=400)
    source = datasource_service.create_source(db, body)
    return JSONResponse({"ok": True, "source": _source_to_dict(source)})


@router.put("/api/{source_id}")
async def api_datasource_update(source_id: int, request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    source = datasource_service.update_source(db, source_id, body)
    if not source:
        return JSONResponse({"error": "数据源不存在"}, status_code=404)
    return JSONResponse({"ok": True, "source": _source_to_dict(source)})


@router.post("/api/{source_id}/toggle")
def api_datasource_toggle(source_id: int, db: Session = Depends(get_db)):
    source = datasource_service.get_source(db, source_id)
    if source:
        datasource_service.update_source(db, source_id, {"enabled": not source.enabled})
    return JSONResponse({"ok": True})


@router.post("/api/{source_id}/test")
def api_datasource_test(source_id: int, db: Session = Depends(get_db)):
    ok, msg = datasource_service.test_source(db, source_id)
    return JSONResponse({"ok": ok, "message": msg})


@router.post("/api/{source_id}/delete")
def api_datasource_delete(source_id: int, db: Session = Depends(get_db)):
    datasource_service.delete_source(db, source_id)
    return JSONResponse({"ok": True})


