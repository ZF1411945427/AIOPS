from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import DataSource, K8sEvent
from app.template_utils import get_templates

router = APIRouter(prefix="/es-integration", tags=["es_integration"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def es_config_page(request: Request, db: Session = Depends(get_db)):
    es_sources = db.query(DataSource).filter(DataSource.type == "elasticsearch").all()
    return templates.TemplateResponse("es_integration.html", {"request": request, "es_sources": es_sources})


@router.post("/sync-events/{ds_id}")
def sync_events_to_es(ds_id: int, db: Session = Depends(get_db)):
    ds = db.query(DataSource).filter(DataSource.id == ds_id, DataSource.type == "elasticsearch").first()
    if not ds:
        return PlainTextResponse("ES data source not found", status_code=404)
    try:
        from elasticsearch import Elasticsearch
        import json
        cfg = json.loads(ds.auth_config) if isinstance(ds.auth_config, str) else ds.auth_config or {}
        username = cfg.get("username")
        password = cfg.get("password")
        api_key = cfg.get("api_key", "")
        if api_key:
            es = Elasticsearch(ds.endpoint, api_key=api_key, request_timeout=30)
        elif username and password:
            es = Elasticsearch(ds.endpoint, basic_auth=(username, password), request_timeout=30)
        else:
            es = Elasticsearch(ds.endpoint, request_timeout=30)

        since = datetime.now() - timedelta(hours=1)
        events = db.query(K8sEvent).filter(K8sEvent.last_seen >= since).all()
        count = 0
        for ev in events:
            doc = {
                "cluster": ev.cluster,
                "namespace": ev.namespace,
                "name": ev.name,
                "kind": ev.kind,
                "reason": ev.reason,
                "message": ev.message,
                "count": ev.count,
                "severity": ev.severity,
                "timestamp": ev.last_seen.isoformat() if ev.last_seen else None,
            }
            es.index(index="aiops-events", body=doc, id=f"k8s_event_{ev.id}")
            count += 1
        es.close()
        return RedirectResponse(f"/es-integration", status_code=303)
    except Exception as e:
        return PlainTextResponse(f"ES sync error: {e}", status_code=500)
