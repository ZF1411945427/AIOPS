import re
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func, text, distinct
from app.template_utils import get_templates

from app.database import get_db
from app.models import MetricRecord
from app.services import metric_service, asset_service
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


@router.get("", response_class=HTMLResponse)
def metrics_page(request: Request, asset_id: int = 0, db: Session = Depends(get_db)):
    assets = asset_service.list_assets(db)
    names = metric_service.get_metric_names(db)
    cat_map = _categorize(names, {})

    # Build category info
    categories_info = []
    for cat in CATEGORIES:
        m_names = cat_map.get(cat["key"], [])
        if m_names:
            categories_info.append({**cat, "names": m_names, "has_data": False})
    if "other" in cat_map and cat_map["other"]:
        categories_info.append({"key": "other", "label": "其他", "icon": "📊", "names": cat_map["other"], "has_data": False})

    return templates.TemplateResponse("metrics.html", {
        "request": request,
        "assets": assets,
        "metric_names": names,
        "selected_asset": asset_id,
        "categories": categories_info,
    })
