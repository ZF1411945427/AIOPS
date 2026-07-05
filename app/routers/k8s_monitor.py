from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from collections import defaultdict
from app.database import get_db
from app.models import Asset, MetricRecord, DataSource

router = APIRouter(prefix="/k8s-monitor", tags=["k8s_monitor"])


@router.get("/api/list")
def api_k8s_monitor_list(cluster: str = "", hours: int = 1, db: Session = Depends(get_db)):
    try:
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
                cluster_info = {
                    "name": ds.name,
                    "endpoint": ds.endpoint,
                    "status": ds.last_status,
                    "last_scrape": str(ds.last_scrape) if ds.last_scrape else None,
                }
        return JSONResponse({
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
            "cluster": cluster,
            "hours": hours,
            "node_count": node_count,
            "pod_count": pod_count,
            "dep_count": dep_count,
            "running_pods": running_pods,
            "node_series": dict(node_series),
            "pod_series": dict(pod_series),
            "cluster_info": cluster_info,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
