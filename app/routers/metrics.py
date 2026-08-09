import re
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, text, distinct
from app.template_utils import get_templates

from app.database import get_db
from app.models import MetricRecord
from app.services import metric_service, asset_service
from app.services import metric_v2_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/metrics", tags=["metrics"])
templates = get_templates()

CATEGORIES = [
    {"key": "cpu", "label": "CPU / 负载", "icon": "⚡", "pattern": r"cpu|loadavg|uptime"},
    {"key": "memory", "label": "内存", "icon": "🧠", "pattern": r"memory|swap"},
    {"key": "disk", "label": "磁盘", "icon": "💿", "pattern": r"^disk"},
    {"key": "network", "label": "网络", "icon": "📥", "pattern": r"net_|network|tcp_"},
    {"key": "system", "label": "系统", "icon": "⚙️", "pattern": r"process_|zombie|open_files|uptime"},
    {"key": "connection", "label": "应用连接", "icon": "🔌", "pattern": r"ssh_conn|http_conn|mysql_conn|_connections"},
    {"key": "docker", "label": "Docker", "icon": "🐳", "pattern": r"docker"},
    {"key": "k8s", "label": "Kubernetes", "icon": "☸️", "pattern": r"deployment|node_|pod_"},
]


def _categorize(metric_names, latest_values=None):
    """Group metric names into categories, with 'other' catch-all. Sorts data-first."""
    if latest_values is None:
        latest_values = {}
    cat_map = {}
    other = []
    for m in metric_names:
        matched = False
        for cat in CATEGORIES:
            if re.search(cat["pattern"], m, re.I):
                cat_map.setdefault(cat["key"], []).append(m)
                matched = True
                break
        if not matched:
            other.append(m)
    for key in cat_map:
        cat_map[key].sort(key=lambda n: (0 if n in latest_values else 1, n))
    if other:
        other.sort(key=lambda n: (0 if n in latest_values else 1, n))
        cat_map["other"] = other
    return cat_map


@router.get("/data")
def metrics_data(asset_id: int = 0, name: str = "", hours: float = 1, db: Session = Depends(get_db)):
    """Return recent metric records (limited, fast)."""
    since = datetime.utcnow() - timedelta(hours=hours)
    MR = MetricRecord
    q = db.query(MR.name, MR.asset_id, MR.value, MR.unit, MR.timestamp).filter(MR.timestamp >= since)
    if asset_id:
        q = q.filter(MR.asset_id == asset_id)
    if name:
        q = q.filter(MR.name == name)
    rows = q.order_by(MR.timestamp.desc()).limit(50000).all()
    return JSONResponse([
        {"time": r.timestamp.isoformat(), "value": r.value, "name": r.name, "asset_id": r.asset_id, "unit": r.unit}
        for r in rows
    ])


@router.get("/latest")
def metrics_latest(asset_id: int = 0, db: Session = Depends(get_db)):
    """Return latest value per metric name (optimized)."""
    since = datetime.utcnow() - timedelta(hours=24)
    MR = MetricRecord
    # Subquery to get max timestamp per metric name
    sub = db.query(
        MR.name,
        func.max(MR.timestamp).label("max_ts")
    ).filter(MR.timestamp >= since)
    if asset_id:
        sub = sub.filter(MR.asset_id == asset_id)
    sub = sub.group_by(MR.name).subquery()

    # Join to get full record for each latest timestamp
    q = db.query(MR).join(sub, (MR.name == sub.c.name) & (MR.timestamp == sub.c.max_ts))
    if asset_id:
        q = q.filter(MR.asset_id == asset_id)
    rows = q.all()
    latest = {}
    for r in rows:
        latest[r.name] = {"value": r.value, "unit": r.unit, "asset_id": r.asset_id, "timestamp": r.timestamp.isoformat() if r.timestamp else ""}
    return JSONResponse(latest)


@router.get("/names")
def metrics_names(db: Session = Depends(get_db)):
    """Return distinct metric names."""
    rows = db.query(MetricRecord.name).distinct().all()
    return JSONResponse(sorted([r[0] for r in rows]))


# === VictoriaMetrics v2 查询接口 ===

@router.get("/api/v2/query")
def metrics_v2_query(q: str = "", asset_id: int = 0):
    """执行 PromQL 查询，返回 VM 查询结果."""
    if not q:
        return JSONResponse({"error": "q 参数必填"}, status_code=400)
    if asset_id > 0:
        q = f'{q}{{asset_id="{asset_id}"}}'
    result = metric_v2_service.query_promql(q)
    return JSONResponse(result)


@router.get("/api/v2/latest")
def metrics_v2_latest(asset_id: int = 0, aggregate: str = ""):
    """查询最新指标值（走 VM）。

    - asset_id=0 + aggregate=avg|sum|max|min: 跨资产聚合值
    - asset_id>0: 返回该资产的最新值
    - asset_id=0 且无 aggregate: 兼容旧行为(返回最后一条)
    """
    if asset_id == 0 and aggregate:
        latest = metric_v2_service.query_latest_aggregated(aggregate=aggregate)
    else:
        latest = metric_v2_service.query_latest_values(asset_id=asset_id if asset_id else None)
    return JSONResponse(latest)


@router.get("/api/v2/range")
def metrics_v2_range(asset_id: int = 0, name: str = "", hours: int = 24, aggregate: str = ""):
    """查询指标历史范围数据（走 VM）。

    - asset_id=0 + aggregate=avg|sum|max|min: 返回 {avg, series} 聚合+明细叠加
    - asset_id>0: 返回该资产的时间序列
    - asset_id=0 且无 aggregate: 返回所有资产数据
    """
    if asset_id == 0 and aggregate:
        if name:
            return JSONResponse(metric_v2_service.query_range_aggregated(name, aggregate=aggregate, hours=hours))
        names = metric_v2_service.query_metric_names()
        merged = {"avg": [], "series": []}
        seen_avg = set()
        seen_series = {}
        for n in names:
            r = metric_v2_service.query_range_aggregated(n, aggregate=aggregate, hours=hours)
            for pt in r.get("avg", []):
                k = pt["time"]
                if k not in seen_avg:
                    merged["avg"].append(pt)
                    seen_avg.add(k)
            for s in r.get("series", []):
                sk = s["asset_id"]
                if sk not in seen_series:
                    seen_series[sk] = s
                    merged["series"].append(s)
        merged["avg"].sort(key=lambda x: x["time"])
        return JSONResponse(merged)
    if name:
        data = metric_v2_service.query_range_data(asset_id=asset_id, name=name, hours=hours)
        return JSONResponse(data)
    names = metric_v2_service.query_metric_names()
    all_data = []
    for n in names:
        all_data.extend(metric_v2_service.query_range_data(asset_id=asset_id, name=n, hours=hours))
    return JSONResponse(all_data)


@router.post("/api/v2/custom-query")
def metrics_v2_custom_query(body: dict):
    """执行自定义 PromQL 查询.

    body: {"promql": "...", "hours": 24}
    """
    promql = body.get("promql", "").strip()
    if not promql:
        return JSONResponse({"error": "promql 必填", "series": []}, status_code=400)
    hours = int(body.get("hours", 24))
    result = metric_v2_service.query_custom_promql(promql, hours=hours)
    return JSONResponse(result)


@router.get("/api/v2/names")
def metrics_v2_names():
    """查询 VM 中所有指标名."""
    names = metric_v2_service.query_metric_names()
    return JSONResponse(sorted(names))


@router.get("/api/v2/status")
def metrics_v2_status():
    """查询 VM 健康状态."""
    available = metric_v2_service.is_vm_available()
    return JSONResponse({"available": available, "url": metric_v2_service.VM_URL})


