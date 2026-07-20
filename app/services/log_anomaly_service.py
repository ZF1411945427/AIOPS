import json
import re
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import LogAnomalyRule, Alert, Asset, DataSource


def check_log_anomalies(db: Session):
    rules = db.query(LogAnomalyRule).filter(LogAnomalyRule.enabled == True).all()
    now = datetime.now()
    new_alerts = []
    for rule in rules:
        since = now - timedelta(minutes=rule.window_minutes)
        if rule.regex_pattern:
            log_records = _fetch_logs(db, rule.source, since, rule.log_level, keyword=rule.keyword)
            count = 0
            for rec in log_records:
                msg = rec.get("message", "")
                try:
                    if re.search(rule.regex_pattern, msg):
                        count += 1
                except Exception:
                    pass
        elif rule.keyword and rule.log_level:
            count = _count_es_logs(db, rule.source, since, rule.log_level, keyword=rule.keyword)
        elif rule.keyword:
            count = _count_es_logs(db, rule.source, since, log_level="", keyword=rule.keyword)
        elif rule.log_level:
            count = _count_es_logs(db, rule.source, since, log_level=rule.log_level, keyword="")
        else:
            count = _count_es_logs(db, rule.source, since, log_level="", keyword="")
        metric_name = f"log_anomaly_{rule.id}"
        existing = (
            db.query(Alert)
            .filter(
                Alert.metric_name == metric_name,
                Alert.status.in_(["triggered", "acknowledged"]),
            )
            .first()
        )
        if count >= rule.threshold:
            if not existing:
                alert = Alert(
                    rule_id=None,
                    metric_name=metric_name,
                    actual_value=float(count),
                    threshold=float(rule.threshold),
                    severity=rule.severity,
                    status="triggered",
                    message=f"日志异常 [{rule.name}]: {count} 条匹配 (窗口={rule.window_minutes}min, 阈值={rule.threshold})",
                )
                db.add(alert)
                new_alerts.append(alert)
            elif existing.status == "acknowledged":
                existing.status = "triggered"
                existing.actual_value = float(count)
                new_alerts.append(existing)
    if new_alerts:
        db.commit()
    return new_alerts


def _fetch_logs(db: Session, source: str, since: datetime, log_level: str = "", keyword: str = ""):
    if source == "k8s":
        from app.models import K8sEvent
        events = (
            db.query(K8sEvent)
            .filter(K8sEvent.last_seen_at >= since)
            .order_by(K8sEvent.last_seen_at.desc())
            .limit(500)
            .all()
        )
        return [{"id": e.id, "message": e.message} for e in events]
    elif source == "metric":
        from app.models import MetricRecord
        records = (
            db.query(MetricRecord)
            .filter(MetricRecord.timestamp >= since)
            .order_by(MetricRecord.timestamp.desc())
            .limit(500)
            .all()
        )
        return [{"id": r.id, "message": f"{r.name}={r.value}"} for r in records]
    elif source == "es" or source.startswith("es:"):
        return _fetch_es_logs(db, source, since, log_level, keyword)
    return []


_es_client_cache = {}
_es_fail_cache = {}  # ds_id -> 失败时间戳，5 分钟内不重试
_ES_FAIL_COOLDOWN = 300  # 5 分钟


def _get_es_client(ds):
    import time as _time
    key = ds.id
    # 失败冷却：5 分钟内不重试不可达的 ES
    if key in _es_fail_cache:
        if _time.time() - _es_fail_cache[key] < _ES_FAIL_COOLDOWN:
            return None
        else:
            del _es_fail_cache[key]
    if key in _es_client_cache:
        try:
            if _es_client_cache[key].ping():
                return _es_client_cache[key]
        except Exception:
            del _es_client_cache[key]
    try:
        from elasticsearch import Elasticsearch
    except ImportError:
        return None
    raw = ds.auth_config
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
            es = Elasticsearch(ds.endpoint, api_key=api_key, request_timeout=3)
        elif auth:
            es = Elasticsearch(ds.endpoint, basic_auth=auth, request_timeout=3)
        else:
            es = Elasticsearch(ds.endpoint, request_timeout=3)
        if es.ping():
            _es_client_cache[key] = es
            return es
        else:
            _es_fail_cache[key] = _time.time()
            return None
    except Exception:
        _es_fail_cache[key] = _time.time()
        return None


def _count_es_logs(db: Session, source: str, since: datetime, log_level: str = "", keyword: str = ""):
    """ES 层聚合计数，仅返回匹配数，不传输文档体（高性能）"""
    ds_id = None
    if source.startswith("es:"):
        try:
            ds_id = int(source.split(":", 1)[1])
        except (ValueError, IndexError):
            return 0

    q = db.query(DataSource).filter(DataSource.type == "elasticsearch", DataSource.enabled == True)
    if ds_id:
        q = q.filter(DataSource.id == ds_id)
    ds = q.first()
    if not ds:
        return 0

    es = _get_es_client(ds)
    if not es:
        return 0

    now = datetime.now()
    must_clauses = []
    if log_level:
        must_clauses.append({"term": {"level.keyword": log_level}})
    if keyword:
        must_clauses.append({"wildcard": {"message": {"value": f"*{keyword}*"}}})
    if not must_clauses:
        must_clauses.append({"match_all": {}})

    es_query = {
        "bool": {
            "must": must_clauses,
            "filter": [{"range": {"@timestamp": {"gte": since.isoformat(), "lte": now.isoformat()}}}],
        }
    }

    try:
        resp = es.count(body={"query": es_query})
        return resp.get("count", 0)
    except Exception:
        return 0


def _fetch_es_logs(db: Session, source: str, since: datetime, log_level: str = "", keyword: str = ""):
    """仅给 regex_pattern 用的回退路径，拉取文档供 Python regex 匹配"""
    ds_id = None
    if source.startswith("es:"):
        try:
            ds_id = int(source.split(":", 1)[1])
        except (ValueError, IndexError):
            return []

    q = db.query(DataSource).filter(DataSource.type == "elasticsearch", DataSource.enabled == True)
    if ds_id:
        q = q.filter(DataSource.id == ds_id)
    ds = q.first()
    if not ds:
        return []

    es = _get_es_client(ds)
    if not es:
        return []

    now = datetime.now()
    must_clauses = []
    if log_level:
        must_clauses.append({"term": {"level.keyword": log_level}})
    if keyword:
        must_clauses.append({"wildcard": {"message": {"value": f"*{keyword}*"}}})
    if not must_clauses:
        must_clauses.append({"match_all": {}})

    es_query = {
        "bool": {
            "must": must_clauses,
            "filter": [{"range": {"@timestamp": {"gte": since.isoformat(), "lte": now.isoformat()}}}],
        }
    }

    try:
        resp = es.search(
            body={
                "query": es_query,
                "sort": [{"@timestamp": {"order": "desc"}}],
                "size": 1000,
            }
        )
        hits = resp.get("hits", {}).get("hits", [])
        results = []
        for hit in hits:
            src = hit.get("_source", {})
            results.append({
                "id": hit.get("_id", ""),
                "message": src.get("message", src.get("log", "")),
            })
        return results
    except Exception:
        return []
