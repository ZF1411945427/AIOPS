import re
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import K8sEvent, ClusterAnomalyEvent, Alert
from app.template_utils import get_templates

router = APIRouter(prefix="/cluster-anomaly", tags=["cluster-anomaly"])
templates = get_templates()


def detect_dns_failures(db: Session) -> list[dict]:
    since = datetime.now() - timedelta(hours=1)
    events = (
        db.query(K8sEvent)
        .filter(K8sEvent.created_at >= since)
        .all()
    )
    dns_events = []
    for ev in events:
        msg = (ev.message or "").lower()
        if any(k in msg for k in ["dns", "resolution", "nameserver", "coredns", "dnsmasq"]):
            dns_events.append(ev)
    count = len(dns_events)
    if count >= 3:
        return [{"type": "dns_failure", "count": count, "message": f"Detected {count} DNS-related events in last hour",
                 "severity": "critical" if count > 10 else "warning"}]
    return []


def detect_cni_errors(db: Session) -> list[dict]:
    since = datetime.now() - timedelta(hours=1)
    events = (
        db.query(K8sEvent)
        .filter(K8sEvent.created_at >= since)
        .all()
    )
    cni_events = []
    for ev in events:
        msg = (ev.message or "").lower()
        if any(k in msg for k in ["cni", "calico", "flannel", "weave", "cilium", "network plugin"]):
            cni_events.append(ev)
    count = len(cni_events)
    if count >= 3:
        return [{"type": "cni_error", "count": count, "message": f"Detected {count} CNI-related events in last hour",
                 "severity": "critical" if count > 10 else "warning"}]
    return []


def detect_node_notready(db: Session) -> list[dict]:
    since = datetime.now() - timedelta(hours=1)
    count = (
        db.query(K8sEvent)
        .filter(K8sEvent.created_at >= since,
                K8sEvent.reason.like("%NodeNotReady%") | K8sEvent.message.like("%NotReady%"))
        .count()
    )
    if count >= 2:
        return [{"type": "node_notready", "count": count, "message": f"Detected {count} NodeNotReady events in last hour",
                 "severity": "critical" if count > 5 else "warning"}]
    return []


@router.get("", response_class=HTMLResponse)
def cluster_anomaly_page(request: Request, db: Session = Depends(get_db)):
    anomalies = db.query(ClusterAnomalyEvent).order_by(desc(ClusterAnomalyEvent.last_seen)).limit(50).all()
    return templates.TemplateResponse("cluster_anomaly.html", {
        "request": request, "anomalies": anomalies, "detect_result": None,
    })


@router.get("/detect", response_class=HTMLResponse)
def run_detection(request: Request, db: Session = Depends(get_db)):
    results = []
    results.extend(detect_dns_failures(db))
    results.extend(detect_cni_errors(db))
    results.extend(detect_node_notready(db))
    now = datetime.now()
    for r in results:
        existing = (
            db.query(ClusterAnomalyEvent)
            .filter(ClusterAnomalyEvent.anomaly_type == r["type"],
                    ClusterAnomalyEvent.resolved == False)
            .first()
        )
        if existing:
            existing.count += r["count"]
            existing.last_seen = now
        else:
            db.add(ClusterAnomalyEvent(
                anomaly_type=r["type"], cluster="default",
                message=r["message"], severity=r["severity"],
                count=r["count"], first_seen=now, last_seen=now,
            ))
        db.add(Alert(
            name=f"Cluster-{r['type']}",
            metric=r["type"],
            message=r["message"],
            severity=r["severity"],
            source="cluster_anomaly",
            status="firing",
        ))
    db.commit()
    anomalies = db.query(ClusterAnomalyEvent).order_by(desc(ClusterAnomalyEvent.last_seen)).limit(50).all()
    return templates.TemplateResponse("cluster_anomaly.html", {
        "request": request, "anomalies": anomalies, "detect_result": results,
    })


@router.get("/resolve/{aid}")
def resolve_anomaly(aid: int, request: Request, db: Session = Depends(get_db)):
    a = db.query(ClusterAnomalyEvent).filter(ClusterAnomalyEvent.id == aid).first()
    if a:
        a.resolved = True
        db.commit()
    return RedirectResponse("/cluster-anomaly", status_code=303)
