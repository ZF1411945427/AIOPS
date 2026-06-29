import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.template_utils import get_templates
from app.models import ApiToken, MetricRecord, K8sEvent, Asset

router = APIRouter(prefix="/api/v1", tags=["api_v1"])
templates = get_templates()


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
        token.last_used = datetime.now()
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
    authorization: str = Header(""),
):
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
            timestamp=ts,
        )
        db.add(record)
        count += 1
    db.commit()
    return {"status": "ok", "accepted": count, "message": f"{count} metrics ingested"}


@router.post("/events")
def push_events(
    data: list[dict],
    db: Session = Depends(get_db),
    authorization: str = Header(""),
):
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
            first_seen=now,
            last_seen=now,
            count=item.get("count", 1),
            severity=item.get("severity", "info"),
        )
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
    authorization: str = Header(""),
):
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


@router.get("/docs", response_class=HTMLResponse)
def api_docs(request: Request):
    return templates.TemplateResponse("api_docs.html", {"request": request})
