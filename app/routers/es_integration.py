from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import DataSource, K8sEvent
from app.template_utils import parse_json_config

router = APIRouter(prefix="/es-integration", tags=["es_integration"])


@router.get("/api/list")
def api_es_list(db: Session = Depends(get_db)):
    es_sources = db.query(DataSource).filter(DataSource.type == "elasticsearch").all()
    return {
        "sources": [
            {
                "id": ds.id, "name": ds.name, "endpoint": ds.endpoint,
                "last_status": ds.last_status, "enabled": ds.enabled,
            }
            for ds in es_sources
        ],
        "count": len(es_sources),
    }


@router.post("/api/sync-events/{ds_id}")
def api_sync_events(ds_id: int, db: Session = Depends(get_db)):
    ds = db.query(DataSource).filter(DataSource.id == ds_id, DataSource.type == "elasticsearch").first()
    if not ds:
        return {"status": "error", "message": "ES 数据源不存在"}
    try:
        from elasticsearch import Elasticsearch
        cfg = parse_json_config(ds.auth_config)
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
        events = db.query(K8sEvent).filter(K8sEvent.last_seen_at >= since).all()
        count = 0
        for ev in events:
            doc = {
                "cluster": ev.cluster, "namespace": ev.namespace, "name": ev.name,
                "kind": ev.kind, "reason": ev.reason, "message": ev.message,
                "count": ev.count, "severity": ev.severity,
                "timestamp": ev.last_seen_at.isoformat() if ev.last_seen_at else None,
            }
            es.index(index="aiops-events", body=doc, id=f"k8s_event_{ev.id}")
            count += 1
        es.close()
        return {"status": "ok", "synced": count}
    except Exception as e:
        return {"status": "error", "message": f"ES 同步失败: {e}"}
