import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.template_utils import get_templates
from app.models import DataSource

router = APIRouter(prefix="/logs", tags=["logs"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def log_viewer(
    request: Request,
    source_id: int = 0,
    query: str = "*",
    time_range: str = "1h",
    page: int = 1,
    size: int = 50,
    db: Session = Depends(get_db),
):
    sources = db.query(DataSource).filter(DataSource.type == "elasticsearch").all()
    logs = []
    total = 0
    error = None
    selected_source = None

    if source_id > 0:
        selected_source = db.query(DataSource).filter(DataSource.id == source_id).first()
        if selected_source:
            try:
                logs, total, error = _query_elasticsearch(selected_source, query, time_range, page, size)
            except Exception as e:
                error = str(e)

    return templates.TemplateResponse("logs.html", {
        "request": request,
        "sources": sources,
        "selected_source_id": source_id,
        "query": query,
        "time_range": time_range,
        "page": page,
        "size": size,
        "logs": logs,
        "total": total,
        "error": error,
    })


def _query_elasticsearch(source, query_str, time_range, page, size):
    try:
        from elasticsearch import Elasticsearch
    except ImportError:
        return [], 0, "elasticsearch Python 鍖呮湭瀹夎"

    cfg = json.loads(source.auth_config) if isinstance(source.auth_config, str) else source.auth_config or {}
    auth = ()
    if cfg.get("username") and cfg.get("password"):
        auth = (cfg["username"], cfg["password"])
    api_key = cfg.get("api_key", "")

    try:
        if api_key:
            es = Elasticsearch(source.endpoint, api_key=api_key, request_timeout=30)
        elif auth:
            es = Elasticsearch(source.endpoint, basic_auth=auth, request_timeout=30)
        else:
            es = Elasticsearch(source.endpoint, request_timeout=30)
    except Exception as e:
        return [], 0, f"杩炴帴澶辫触: {e}"

    # Time range
    now = datetime.now()
    if time_range == "15m":
        since = now - timedelta(minutes=15)
    elif time_range == "30m":
        since = now - timedelta(minutes=30)
    elif time_range == "6h":
        since = now - timedelta(hours=6)
    elif time_range == "24h":
        since = now - timedelta(hours=24)
    elif time_range == "7d":
        since = now - timedelta(days=7)
    else:  # 1h
        since = now - timedelta(hours=1)

    # Build ES query
    es_query = {
        "bool": {
            "must": [
                {"query_string": {"query": query_str}} if query_str and query_str != "*" else {"match_all": {}},
                {"range": {"@timestamp": {"gte": since.isoformat(), "lte": now.isoformat()}}}
            ]
        }
    } if query_str and query_str != "*" else {
        "bool": {
            "must": [{"match_all": {}}],
            "filter": [{"range": {"@timestamp": {"gte": since.isoformat(), "lte": now.isoformat()}}}]
        }
    }

    try:
        # Get total count
        count_resp = es.count(body={"query": es_query})
        total = count_resp.get("count", 0)

        # Search with pagination
        from_idx = (page - 1) * size
        resp = es.search(
            body={
                "query": es_query,
                "sort": [{"@timestamp": {"order": "desc"}}],
                "from": from_idx,
                "size": size,
            }
        )
        hits = resp.get("hits", {}).get("hits", [])
        logs = []
        for hit in hits:
            src = hit.get("_source", {})
            logs.append({
                "id": hit.get("_id", ""),
                "index": hit.get("_index", ""),
                "timestamp": src.get("@timestamp", src.get("timestamp", "")),
                "message": src.get("message", src.get("log", json.dumps(src, ensure_ascii=False))),
                "level": src.get("level", src.get("severity", src.get("log_level", "info"))),
                "host": (src.get("host", {}).get("name", "") if isinstance(src.get("host"), dict) else src.get("host", src.get("hostname", ""))),
                "service": (src.get("service", {}).get("name", "") if isinstance(src.get("service"), dict) else src.get("service", src.get("service_name", ""))),
                "source": src,
            })
        es.close()
        return logs, total, None
    except Exception as e:
        try:
            es.close()
        except Exception:
            pass
        return [], 0, f"鏌ヨ澶辫触: {e}"

