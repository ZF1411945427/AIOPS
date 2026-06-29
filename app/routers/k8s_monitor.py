import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from collections import defaultdict
from app.database import get_db
from app.models import Asset, MetricRecord, DataSource
from app.template_utils import get_templates

router = APIRouter(prefix="/k8s-monitor", tags=["k8s_monitor"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def k8s_monitor(request: Request, cluster: str = "", hours: int = 1, db: Session = Depends(get_db)):
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    now = datetime.now()
    since = now - timedelta(hours=hours)

    nodes = db.query(Asset).filter(Asset.ci_type == "node")
    pods = db.query(Asset).filter(Asset.ci_type == "pod")
    deps = db.query(Asset).filter(Asset.ci_type == "deployment")
    if cluster:
        nodes = nodes.filter(Asset.k8s_cluster == cluster)
        pods = pods.filter(Asset.k8s_cluster == cluster)
        deps = deps.filter(Asset.k8s_cluster == cluster)

    node_count = nodes.count()
    pod_count = pods.count()
    dep_count = deps.count()
    running_pods = pods.filter(Asset.status == "online").count()

    metrics = (
        db.query(MetricRecord)
        .filter(MetricRecord.timestamp >= since)
        .order_by(MetricRecord.timestamp.asc())
        .all()
    )

    node_series = defaultdict(list)
    pod_series = defaultdict(list)
    for m in metrics:
        if m.name.startswith("node_cpu_"):
            node_series["cpu"].append({"t": m.timestamp.isoformat(), "v": m.value})
        elif m.name.startswith("node_memory_"):
            node_series["memory"].append({"t": m.timestamp.isoformat(), "v": m.value})
        elif m.name.startswith("pod_restarts"):
            pod_series["restarts"].append({"t": m.timestamp.isoformat(), "v": m.value})
        elif m.name.startswith("deployment_replicas"):
            pod_series["replicas"].append({"t": m.timestamp.isoformat(), "v": m.value})

    cluster_info = None
    if cluster:
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        if ds:
            cluster_info = {"name": ds.name, "endpoint": ds.endpoint, "status": ds.last_status, "last_scrape": ds.last_scrape}
    return templates.TemplateResponse("k8s_monitor.html", {
        "request": request,
        "clusters": clusters,
        "cluster": cluster,
        "hours": hours,
        "node_count": node_count,
        "pod_count": pod_count,
        "dep_count": dep_count,
        "running_pods": running_pods,
        "node_series": json.dumps(node_series, ensure_ascii=False),
        "pod_series": json.dumps(pod_series, ensure_ascii=False),
        "cluster_info": cluster_info,
    })
