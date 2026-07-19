import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.template_utils import get_templates
from app.models import DataSource

router = APIRouter(prefix="/logs", tags=["logs"])
templates = get_templates()


# ─── JSON API（供 Vue 前端调用，保留 HTML 路由作 fallback）───

@router.get("/api/sources")
def api_log_sources(db: Session = Depends(get_db)):
    """返回 ES 类型数据源列表."""
    sources = db.query(DataSource).filter(DataSource.type == "elasticsearch").all()
    return JSONResponse([{
        "id": s.id, "name": s.name, "endpoint": s.endpoint or "",
        "enabled": bool(s.enabled),
    } for s in sources])


@router.get("/api/search")
def api_log_search(
    source_id: int = 0,
    query: str = "*",
    time_range: str = "1h",
    page: int = 1,
    size: int = 50,
    index: str = "",
    level: str = "",
    host: str = "",
    service: str = "",
    db: Session = Depends(get_db)):
    """日志搜索 JSON API，支持高级过滤."""
    if source_id <= 0:
        return JSONResponse({"logs": [], "total": 0, "page": page, "size": size, "error": None, "total_pages": 1})
    source = db.query(DataSource).filter(DataSource.id == source_id).first()
    if not source:
        return JSONResponse({"logs": [], "total": 0, "page": page, "size": size, "error": "数据源不存在", "total_pages": 1})
    try:
        logs, total, error = _query_elasticsearch(source, query, time_range, page, size, index, level, host, service)
    except Exception as e:
        logs, total, error = [], 0, str(e)
    total_pages = (total + size - 1) // size if total > 0 else 1
    return JSONResponse({
        "logs": logs, "total": total, "page": page, "size": size,
        "error": error, "total_pages": total_pages,
    })

@router.get("/api/indices")
def api_log_indices(source_id: int = 0, db: Session = Depends(get_db)):
    """返回 ES 数据源的索引列表."""
    if source_id <= 0:
        return JSONResponse([])
    source = db.query(DataSource).filter(DataSource.id == source_id).first()
    if not source:
        return JSONResponse([])
    try:
        from elasticsearch import Elasticsearch
        raw = source.auth_config
        if isinstance(raw, str) and raw.strip():
            cfg = json.loads(raw)
        elif isinstance(raw, dict):
            cfg = raw
        else:
            cfg = {}
        auth, api_key = (), ""
        if cfg.get("username") and cfg.get("password"):
            auth = (cfg["username"], cfg["password"])
        api_key = cfg.get("api_key", "")
        if api_key:
            es = Elasticsearch(source.endpoint, api_key=api_key, request_timeout=5)
        elif auth:
            es = Elasticsearch(source.endpoint, basic_auth=auth, request_timeout=5)
        else:
            es = Elasticsearch(source.endpoint, request_timeout=5)
        indices = es.cat.indices(format="json", h="index,docs.count")
        es.close()
        return JSONResponse([{"name": i["index"], "docs": int(i.get("docs.count", 0))} for i in indices])
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


def _query_elasticsearch(source, query_str, time_range, page, size, index="", level="", host="", service=""):
    try:
        from elasticsearch import Elasticsearch
    except ImportError:
        return [], 0, "elasticsearch Python 库未安装，请运行: pip install elasticsearch"

    import socket
    from urllib.parse import urlparse
    try:
        parsed = urlparse(source.endpoint)
        hostname = parsed.hostname or "127.0.0.1"
        port = parsed.port or 9200
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((hostname, port))
        sock.close()
        if result != 0:
            return [], 0, f"无法连接到 Elasticsearch {hostname}:{port}（连接超时或被拒绝），请检查数据源地址和网络连通性。"
    except Exception as e:
        return [], 0, f"ES 地址解析失败: {e}"

    raw = source.auth_config
    if isinstance(raw, str) and raw.strip():
        try:
            cfg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            cfg = {}
    elif isinstance(raw, dict):
        cfg = raw
    else:
        cfg = {}
    auth = ()
    if cfg.get("username") and cfg.get("password"):
        auth = (cfg["username"], cfg["password"])
    api_key = cfg.get("api_key", "")

    try:
        if api_key:
            es = Elasticsearch(source.endpoint, api_key=api_key, request_timeout=8)
        elif auth:
            es = Elasticsearch(source.endpoint, basic_auth=auth, request_timeout=8)
        else:
            es = Elasticsearch(source.endpoint, request_timeout=8)
    except Exception as e:
        return [], 0, f"ES 连接失败: {e}"

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
    else:
        since = now - timedelta(hours=1)

    filters = [{"range": {"@timestamp": {"gte": since.isoformat(), "lte": now.isoformat()}}}]
    if level:
        levels = [l.strip() for l in level.split(",") if l.strip()]
        if len(levels) == 1:
            filters.append({"term": {"level.keyword": levels[0]}})
        elif len(levels) > 1:
            filters.append({"terms": {"level.keyword": levels}})
    if host:
        filters.append({"wildcard": {"host": {"value": f"*{host}*"}}})
    if service:
        filters.append({"wildcard": {"service": {"value": f"*{service}*"}}})

    must_clause = [{"query_string": {"query": query_str}}] if query_str and query_str != "*" else [{"match_all": {}}]
    es_query = {"bool": {"must": must_clause, "filter": filters}}

    try:
        es_index = index if index else "_all"
        count_resp = es.count(index=es_index, body={"query": es_query})
        total = count_resp.get("count", 0)

        from_idx = (page - 1) * size
        resp = es.search(
            index=es_index,
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
        return [], 0, f"ES 查询失败: {e}"

