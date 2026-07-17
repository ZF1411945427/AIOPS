import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApiToken, MetricRecord, K8sEvent, Asset

router = APIRouter(prefix="/api/v1", tags=["api_v1"])


def _verify_token(authorization: str = Header("")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token_str = authorization[7:]
    from app.database import get_session_for, get_db_mode
    db = get_session_for(get_db_mode())()
    try:
        token = db.query(ApiToken).filter(ApiToken.token == token_str, ApiToken.enabled == True).first()
        if not token:
            raise HTTPException(status_code=403, detail="Invalid or disabled token")
        token.last_used_at = datetime.now()
        db.commit()
        return token.permissions
    finally:
        db.close()


def _require_permission(perm: str, perms: str):
    if perms not in ("admin", perm):
        raise HTTPException(status_code=403, detail=f"Token requires '{perm}' permission")


@router.post("/metrics")
def push_metrics(
    data: list[dict],
    db: Session = Depends(get_db),
    authorization: str = Header("")):
    perms = _verify_token(authorization)
    _require_permission("write", perms)
    now = datetime.now()
    count = 0
    for item in data:
        name = item.get("name", "")
        value = item.get("value")
        if not name or value is None:
            continue
        asset_name = item.get("asset", "")
        asset_id = None
        if asset_name:
            asset = db.query(Asset).filter(Asset.name == asset_name).first()
            if asset:
                asset_id = asset.id
        ts = item.get("timestamp", None)
        if ts:
            try:
                ts = datetime.fromisoformat(ts)
            except Exception:
                ts = now
        else:
            ts = now
        labels = item.get("labels", {})
        record = MetricRecord(
            asset_id=asset_id,
            name=name,
            value=float(value),
            unit=item.get("unit", ""),
            labels=json.dumps(labels, ensure_ascii=False),
            timestamp=ts)
        db.add(record)
        count += 1
    db.commit()
    return {"status": "ok", "accepted": count, "message": f"{count} metrics ingested"}


@router.post("/events")
def push_events(
    data: list[dict],
    db: Session = Depends(get_db),
    authorization: str = Header("")):
    perms = _verify_token(authorization)
    _require_permission("write", perms)
    now = datetime.now()
    count = 0
    for item in data:
        event = K8sEvent(
            cluster=item.get("cluster", "external"),
            namespace=item.get("namespace", "default"),
            name=item.get("name", ""),
            kind=item.get("kind", "Event"),
            reason=item.get("reason", ""),
            message=item.get("message", ""),
            source=item.get("source", "api"),
            first_seen_at=now,
            last_seen_at=now,
            count=item.get("count", 1),
            severity=item.get("severity", "info"))
        db.add(event)
        count += 1
    db.commit()
    return {"status": "ok", "accepted": count, "message": f"{count} events ingested"}


@router.get("/query/metrics")
def query_metrics(
    name: str = "",
    asset: str = "",
    hours: int = 1,
    limit: int = 100,
    db: Session = Depends(get_db),
    authorization: str = Header("")):
    perms = _verify_token(authorization)
    _require_permission("read", perms)
    q = db.query(MetricRecord)
    if name:
        q = q.filter(MetricRecord.name == name)
    if asset:
        asset_obj = db.query(Asset).filter(Asset.name == asset).first()
        if asset_obj:
            q = q.filter(MetricRecord.asset_id == asset_obj.id)
    since = datetime.now()
    try:
        from datetime import timedelta
        since = datetime.now() - timedelta(hours=hours)
    except Exception:
        pass
    q = q.filter(MetricRecord.timestamp >= since)
    records = q.order_by(MetricRecord.timestamp.desc()).limit(limit).all()
    return JSONResponse([{
        "id": r.id,
        "name": r.name,
        "value": r.value,
        "unit": r.unit,
        "labels": json.loads(r.labels) if r.labels else {},
        "timestamp": r.timestamp.isoformat(),
        "asset_id": r.asset_id,
    } for r in records])


@router.get("/api/docs")
def api_docs_meta(db: Session = Depends(get_db)):
    try:
        endpoints = [
            {
                "method": "POST",
                "path": "/api/v1/metrics",
                "summary": "推送指标数据",
                "auth": "Bearer Token (write)",
                "body_example": [{"name": "cpu_usage", "value": 78.5, "asset": "web-01", "unit": "%", "labels": {"host": "web-01"}, "timestamp": "2026-07-05T10:00:00"}],
                "response_example": {"status": "ok", "accepted": 1, "message": "1 metrics ingested"},
            },
            {
                "method": "POST",
                "path": "/api/v1/events",
                "summary": "推送 K8s 事件",
                "auth": "Bearer Token (write)",
                "body_example": [{"cluster": "prod", "namespace": "default", "name": "pod-xxx", "reason": "FailedScheduling", "message": "0/3 nodes available", "severity": "warning"}],
                "response_example": {"status": "ok", "accepted": 1, "message": "1 events ingested"},
            },
            {
                "method": "GET",
                "path": "/api/v1/query/metrics",
                "summary": "查询指标数据",
                "auth": "Bearer Token (read)",
                "params": {"name": "指标名(可选)", "asset": "资产名(可选)", "hours": "回溯小时数(默认1)", "limit": "返回条数(默认100)"},
                "response_example": [{"id": 1, "name": "cpu_usage", "value": 78.5, "unit": "%", "labels": {}, "timestamp": "2026-07-05T10:00:00", "asset_id": 1}],
            },
        ]
        tokens = db.query(ApiToken).all()
        token_list = [{
            "id": t.id,
            "name": t.name,
            "permissions": t.permissions,
            "enabled": t.enabled,
            "last_used_at": t.last_used_at.strftime("%Y-%m-%d %H:%M:%S") if t.last_used_at else None,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else None,
        } for t in tokens]
        return JSONResponse({
            "title": "AIOps 开放接口文档",
            "version": "v1",
            "base_url": "/api/v1",
            "auth": {
                "type": "Bearer Token",
                "header": "Authorization: Bearer <token>",
                "permissions": ["read", "write", "admin"],
            },
            "endpoints": endpoints,
            "tokens": token_list,
            "examples": {
                "curl_push_metrics": 'curl -X POST http://host:8000/api/v1/metrics -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d \'[{"name":"cpu","value":80,"asset":"web-01"}]\'',
                "curl_query_metrics": 'curl "http://host:8000/api/v1/query/metrics?name=cpu&hours=1" -H "Authorization: Bearer <token>"',
            },
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
