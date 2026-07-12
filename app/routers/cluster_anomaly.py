import re
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends, Request
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


@router.get("/status")
def status():
    return {"module": "cluster_anomaly", "status": "ok"}


@router.get("/detect")
def detect_all(db: Session = Depends(get_db)):
    results = []
    results.extend(detect_dns_failures(db))
    results.extend(detect_cni_errors(db))
    results.extend(detect_node_notready(db))
    return {"anomalies": results}


