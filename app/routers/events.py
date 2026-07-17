from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.database import get_db
from app.template_utils import get_templates
from app.models import K8sEvent

router = APIRouter(prefix="/events", tags=["events"])
templates = get_templates()


def _event_to_dict(e: K8sEvent) -> dict:
    return {
        "id": e.id,
        "cluster": e.cluster or "",
        "namespace": e.namespace or "",
        "name": e.name or "",
        "kind": e.kind or "",
        "reason": e.reason or "",
        "message": e.message or "",
        "source": e.source or "",
        "first_seen_at": e.first_seen_at.strftime("%Y-%m-%d %H:%M:%S") if e.first_seen_at else None,
        "last_seen_at": e.last_seen_at.strftime("%Y-%m-%d %H:%M:%S") if e.last_seen_at else None,
        "count": e.count or 1,
        "severity": e.severity or "info",
        "created_at": e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else None,
    }


@router.get("/api/list")
def api_event_list(
    cluster: str = "",
    kind: str = "",
    severity: str = "",
    search: str = "",
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    db: Session = Depends(get_db)):
    """K8s 集群事件列表 JSON API."""
    q = db.query(K8sEvent)
    if cluster:
        q = q.filter(K8sEvent.cluster == cluster)
    if kind:
        q = q.filter(K8sEvent.kind == kind)
    if severity:
        q = q.filter(K8sEvent.severity == severity)
    if search:
        q = q.filter(
            K8sEvent.name.ilike(f"%{search}%")
            | K8sEvent.message.ilike(f"%{search}%")
            | K8sEvent.reason.ilike(f"%{search}%")
        )
    total = q.count()
    events = q.order_by(desc(K8sEvent.last_seen_at)).offset((page - 1) * per_page).limit(per_page).all()
    clusters = sorted(set(c[0] for c in db.query(K8sEvent.cluster).distinct().all() if c[0]))
    kinds = sorted(set(k[0] for k in db.query(K8sEvent.kind).distinct().all() if k[0]))
    total_pages = max(1, (total + per_page - 1) // per_page) if total > 0 else 1
    return JSONResponse({
        "events": [_event_to_dict(e) for e in events],
        "clusters": clusters,
        "kinds": kinds,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    })


@router.get("/api/stats")
def api_event_stats(db: Session = Depends(get_db)):
    """事件统计 JSON API."""
    total = db.query(func.count(K8sEvent.id)).scalar() or 0
    warnings = db.query(func.count(K8sEvent.id)).filter(K8sEvent.severity == "warning").scalar() or 0
    criticals = db.query(func.count(K8sEvent.id)).filter(K8sEvent.severity == "critical").scalar() or 0
    infos = db.query(func.count(K8sEvent.id)).filter(K8sEvent.severity == "info").scalar() or 0
    by_kind = db.query(K8sEvent.kind, func.count(K8sEvent.id)).group_by(K8sEvent.kind).order_by(desc(func.count(K8sEvent.id))).limit(10).all()
    by_reason = db.query(K8sEvent.reason, func.count(K8sEvent.id)).group_by(K8sEvent.reason).order_by(desc(func.count(K8sEvent.id))).limit(10).all()
    return JSONResponse({
        "total": total,
        "warnings": warnings,
        "criticals": criticals,
        "infos": infos,
        "by_kind": [{"kind": k or "未知", "count": c} for k, c in by_kind],
        "by_reason": [{"reason": r or "未知", "count": c} for r, c in by_reason],
    })
