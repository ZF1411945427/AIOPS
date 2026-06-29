from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.template_utils import get_templates
from app.models import K8sEvent

router = APIRouter(prefix="/events", tags=["events"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def event_list(
    request: Request,
    cluster: str = "",
    kind: str = "",
    severity: str = "",
    search: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=10, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(K8sEvent)
    if cluster:
        q = q.filter(K8sEvent.cluster == cluster)
    if kind:
        q = q.filter(K8sEvent.kind == kind)
    if severity:
        q = q.filter(K8sEvent.severity == severity)
    if search:
        q = q.filter(
            K8sEvent.name.ilike(f"%{search}%") |
            K8sEvent.message.ilike(f"%{search}%") |
            K8sEvent.reason.ilike(f"%{search}%")
        )
    total = q.count()
    events = q.order_by(desc(K8sEvent.last_seen)).offset((page - 1) * size).limit(size).all()
    clusters = db.query(K8sEvent.cluster).distinct().all()
    clusters = sorted(set(c[0] for c in clusters if c[0]))
    kinds = db.query(K8sEvent.kind).distinct().all()
    kinds = sorted(set(k[0] for k in kinds if k[0]))
    return templates.TemplateResponse("events.html", {
        "request": request,
        "events": events,
        "clusters": clusters,
        "kinds": kinds,
        "filter_cluster": cluster,
        "filter_kind": kind,
        "filter_severity": severity,
        "search": search,
        "page": page,
        "size": size,
        "total": total,
        "total_pages": max(1, (total + size - 1) // size),
    })


@router.get("/stats", response_class=HTMLResponse)
def event_stats(request: Request, db: Session = Depends(get_db)):
    from sqlalchemy import func
    total = db.query(func.count(K8sEvent.id)).scalar() or 0
    warnings = db.query(func.count(K8sEvent.id)).filter(K8sEvent.severity == "warning").scalar() or 0
    criticals = db.query(func.count(K8sEvent.id)).filter(K8sEvent.severity == "critical").scalar() or 0
    by_kind = db.query(K8sEvent.kind, func.count(K8sEvent.id)).group_by(K8sEvent.kind).order_by(desc(func.count(K8sEvent.id))).limit(10).all()
    by_reason = db.query(K8sEvent.reason, func.count(K8sEvent.id)).group_by(K8sEvent.reason).order_by(desc(func.count(K8sEvent.id))).limit(10).all()
    return templates.TemplateResponse("event_stats.html", {
        "request": request,
        "total": total,
        "warnings": warnings,
        "criticals": criticals,
        "by_kind": by_kind,
        "by_reason": by_reason,
    })
