import re
from datetime import datetime, timedelta
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import Alert, Asset, MetricRecord, K8sEvent, Incident, KnowledgeBase
from app.services.mcp_registry import register_mcp_tool, get_internal_tools, get_mcp_tool
from app.services import remediation_service, alert_service, incident_service, asset_service, rag_service
from app.services.promql_parser import parse_promql, promql_to_dict


import logging
logger = logging.getLogger(__name__)

def _get_db():
    return get_session_for(get_db_mode())()

# ─── Alert Tools ───────────────────────────────────────────────

@register_mcp_tool(
    name="query_alerts",
    description="查询告警列表，支持按状态、级别、资产ID、时间范围筛选",
    input_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "告警状态: triggered, acknowledged, resolved"},
            "severity": {"type": "string", "description": "严重级别: warning, critical"},
            "asset_id": {"type": "integer", "description": "资产 ID（可选，查询该资产的所有告警）"},
            "hours": {"type": "integer", "description": "查询最近多少小时的告警（可选，默认查所有）"},
            "limit": {"type": "integer", "description": "返回数量限制", "default": 10},
        },
    },
    risk_level="read_only",
    display_name="查询告警",
    location="cloud",
    category="alert",
    metric_enabled=True,
)
def query_alerts(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        query = db.query(Alert)
        if kwargs.get("status"):
            query = query.filter(Alert.status == kwargs["status"])
        if kwargs.get("severity"):
            query = query.filter(Alert.severity == kwargs["severity"])
        if kwargs.get("asset_id"):
            query = query.filter(Alert.asset_id == kwargs["asset_id"])
        if kwargs.get("hours"):
            cutoff = datetime.now() - timedelta(hours=int(kwargs["hours"]))
            query = query.filter(Alert.created_at >= cutoff)
        limit = kwargs.get("limit", 10)
        alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()
        return {
            "count": len(alerts),
            "alerts": [
                {
                    "id": a.id,
                    "asset_id": a.asset_id,
                    "metric_name": a.metric_name,
                    "actual_value": a.actual_value,
                    "threshold": a.threshold,
                    "severity": a.severity,
                    "status": a.status,
                    "message": a.message,
                    "created_at": str(a.created_at),
                }
                for a in alerts
            ],
        }
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="get_alert_detail",
    description="查询单个告警的详细信息",
    input_schema={
        "type": "object",
        "properties": {
            "alert_id": {"type": "integer", "description": "告警 ID"},
        },
        "required": ["alert_id"],
    },
    risk_level="read_only",
    display_name="告警详情",
    location="cloud",
    category="alert",
)
def get_alert_detail(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        alert = db.query(Alert).filter(Alert.id == kwargs.get("alert_id")).first()
        if not alert:
            return {"error": "告警未找到"}
        return {
            "id": alert.id,
            "metric_name": alert.metric_name,
            "actual_value": alert.actual_value,
            "threshold": alert.threshold,
            "severity": alert.severity,
            "status": alert.status,
            "message": alert.message,
            "created_at": str(alert.created_at),
            "resolved_at": str(alert.resolved_at) if alert.resolved_at else None,
        }
    finally:
        if close_db:
            db.close()
# ─── Asset Tools ───────────────────────────────────────────────

@register_mcp_tool(
    name="query_assets",
    description="查询资产列表，支持按类型、状态、名称搜索。注意：server、cloud_host、vm 都是服务器类型，搜索主机时可不传 ci_type，用 search 关键字匹配名称/IP。",
    input_schema={
        "type": "object",
        "properties": {
            "ci_type": {"type": "string", "description": "资产类型: server, cloud_host, vm, pod, deployment, service, database 等。搜索主机时可不传，会返回所有类型"},
            "status": {"type": "string", "description": "状态: online, offline, warning"},
            "search": {"type": "string", "description": "名称或IP搜索关键字"},
            "limit": {"type": "integer", "description": "返回数量限制", "default": 20},
        },
    },
    risk_level="read_only",
    display_name="查询资产",
    location="cloud",
    category="asset",
)
def query_assets(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        query = db.query(Asset)
        if kwargs.get("ci_type"):
            query = query.filter(Asset.ci_type == kwargs["ci_type"])
        if kwargs.get("status"):
            query = query.filter(Asset.status == kwargs["status"])
        if kwargs.get("search"):
            from sqlalchemy import or_
            search = kwargs["search"]
            query = query.filter(or_(
                Asset.name.ilike(f"%{search}%"),
                Asset.ip.ilike(f"%{search}%"),
                Asset.tags.ilike(f"%{search}%"),
            ))
        limit = kwargs.get("limit", 20)
        assets = query.order_by(Asset.name).limit(limit).all()
        return {
            "count": len(assets),
            "assets": [
                {
                    "id": a.id,
                    "name": a.name,
                    "ci_type": a.ci_type,
                    "ip": a.ip,
                    "status": a.status,
                    "tags": a.tags,
                    "k8s_cluster": a.k8s_cluster,
                }
                for a in assets
            ],
        }
    finally:
        if close_db:
            db.close()
# ─── Metric Tools ──────────────────────────────────────────────

@register_mcp_tool(
    name="query_metrics",
    description="查询指标最新值或历史趋势。支持两种模式：1) 字段模式（metric_name + asset_id + hours + limit）；2) PromQL 模式（传 promql 参数，如 topk(3, cpu_usage)、rate(cpu_usage[5m])、avg(memory_usage)、cpu_usage{asset_id=\"1\"}）。PromQL 模式支持 topk/bottomk/rate/avg_over_time/avg/max/min/sum 及标签过滤。",
    input_schema={
        "type": "object",
        "properties": {
            "metric_name": {"type": "string", "description": "指标名称，如 cpu_usage, memory_usage, disk_usage（字段模式）"},
            "asset_id": {"type": "integer", "description": "资产 ID（可选，字段模式）"},
            "hours": {"type": "integer", "description": "查询最近多少小时的数据（字段模式，默认 1）"},
            "limit": {"type": "integer", "description": "返回数据点数量（字段模式，默认 60）"},
            "promql": {"type": "string", "description": "PromQL 子集表达式（可选，传入则忽略其他参数）。示例：topk(3, cpu_usage) / rate(cpu_usage[5m]) / avg(memory_usage) / cpu_usage{asset_id=\"1\"}"},
        },
    },
    risk_level="read_only",
    display_name="查询指标",
    location="cloud",
    category="metric",
    timeout_seconds=10,
    ratelimit_per_minute=120,
)
def query_metrics(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        promql_expr = kwargs.get("promql") or ""
        if promql_expr.strip():
            return _query_metrics_promql(db, promql_expr)
        return _query_metrics_field(db, kwargs)
    finally:
        if close_db:
            db.close()


def _query_metrics_field(db: Session, kwargs: Dict) -> Dict:
    """字段模式：按 metric_name + asset_id + hours 查询。"""
    metric_name = kwargs.get("metric_name", "")
    asset_id = kwargs.get("asset_id")
    hours = kwargs.get("hours", 1)
    limit = kwargs.get("limit", 60)

    query = db.query(MetricRecord).filter(MetricRecord.name == metric_name)
    if asset_id:
        query = query.filter(MetricRecord.asset_id == asset_id)
    cutoff = datetime.now() - timedelta(hours=hours)
    query = query.filter(MetricRecord.timestamp >= cutoff)
    records = query.order_by(MetricRecord.timestamp.desc()).limit(limit).all()

    values = [{"value": r.value, "time": str(r.timestamp.strftime("%Y-%m-%d %H:%M:%S")) if r.timestamp else None} for r in records]
    values.reverse()

    avg_value = sum(r.value for r in records) / len(records) if records else 0
    max_value = max(r.value for r in records) if records else 0
    min_value = min(r.value for r in records) if records else 0

    return {
        "metric_name": metric_name,
        "mode": "field",
        "count": len(values),
        "avg": round(avg_value, 2),
        "max": round(max_value, 2),
        "min": round(min_value, 2),
        "latest": values[-1] if values else None,
        "values": values,
    }


def _query_metrics_promql(db: Session, expr: str) -> Dict:
    """PromQL 模式：解析表达式后按聚合类型执行查询。"""
    q = parse_promql(expr)
    if q.error:
        return {"mode": "promql", "error": q.error, "raw": expr}
    if not q.metric_name:
        return {"mode": "promql", "error": "缺少指标名", "raw": expr}

    # 时间窗口默认 1 小时
    hours = 1
    if q.range_window:
        secs = _window_to_seconds(q.range_window)
        if secs:
            hours = max(secs / 3600.0, 0.0167)  # 最少 1 分钟
    cutoff = datetime.now() - timedelta(hours=hours)

    base_q = db.query(MetricRecord).filter(
        MetricRecord.name == q.metric_name,
        MetricRecord.timestamp >= cutoff,
    )
    # 标签过滤
    asset_id_filter = None
    for k, v in q.labels.items():
        if k in ("asset_id", "asset"):
            try:
                asset_id_filter = int(v)
            except ValueError as _exc:
                logger.warning("[except:pass] ValueError: %s", _exc, exc_info=True)
    if asset_id_filter:
        base_q = base_q.filter(MetricRecord.asset_id == asset_id_filter)

    records = base_q.order_by(MetricRecord.timestamp.desc()).limit(2000).all()

    if not records:
        return {
            "mode": "promql", "promql": expr, "metric_name": q.metric_name,
            "aggregator": q.aggregator, "count": 0, "message": "无数据",
            "parsed": promql_to_dict(q),
        }

    # 按资产分组
    by_asset: Dict[int, list] = {}
    for r in records:
        by_asset.setdefault(r.asset_id or 0, []).append(r)

    agg = q.aggregator

    # ── 无聚合：返回最近值列表 ──
    if agg is None:
        latest_per_asset = []
        for aid, rs in by_asset.items():
            latest = rs[0]  # 已按时间倒序
            latest_per_asset.append({
                "asset_id": aid,
                "value": latest.value,
                "unit": latest.unit,
                "time": str(latest.timestamp.strftime("%Y-%m-%d %H:%M:%S")) if latest.timestamp else None,
            })
        return {
            "mode": "promql", "promql": expr, "metric_name": q.metric_name,
            "aggregator": None, "count": len(latest_per_asset),
            "series": latest_per_asset, "parsed": promql_to_dict(q),
        }

    # ── 全资产聚合：avg/max/min/sum/count ──
    if agg in ("avg", "max", "min", "sum", "count"):
        all_vals = [r.value for r in records]
        if agg == "avg":
            v = sum(all_vals) / len(all_vals) if all_vals else 0
        elif agg == "max":
            v = max(all_vals) if all_vals else 0
        elif agg == "min":
            v = min(all_vals) if all_vals else 0
        elif agg == "sum":
            v = sum(all_vals)
        else:  # count
            v = len(all_vals)
        return {
            "mode": "promql", "promql": expr, "metric_name": q.metric_name,
            "aggregator": agg, "value": round(v, 4), "asset_count": len(by_asset),
            "sample_count": len(all_vals), "parsed": promql_to_dict(q),
        }

    # ── topk / bottomk：按资产最近值排序取 N ──
    if agg in ("topk", "bottomk"):
        n = q.aggregator_arg or 3
        # 嵌套聚合：如果内层是 rate/avg_over_time 等（inner_aggregator 不为 None），先算内层再排序
        if q.inner_aggregator:
            inner_series = _compute_range_aggregation(by_asset, q.inner_aggregator, q.range_window)
            reverse = (agg == "topk")
            inner_series.sort(key=lambda x: x.get("value", x.get("rate", 0)), reverse=reverse)
            top = inner_series[:n]
            return {
                "mode": "promql", "promql": expr, "metric_name": q.metric_name,
                "aggregator": agg, "n": n, "inner_aggregator": q.inner_aggregator,
                "window": q.range_window, "count": len(top),
                "series": top, "parsed": promql_to_dict(q),
            }
        latest_per_asset = []
        for aid, rs in by_asset.items():
            latest = rs[0]
            latest_per_asset.append({"asset_id": aid, "value": latest.value, "unit": latest.unit,
                                     "time": str(latest.timestamp.strftime("%Y-%m-%d %H:%M:%S")) if latest.timestamp else None})
        reverse = (agg == "topk")
        latest_per_asset.sort(key=lambda x: x["value"], reverse=reverse)
        top = latest_per_asset[:n]
        return {
            "mode": "promql", "promql": expr, "metric_name": q.metric_name,
            "aggregator": agg, "n": n, "count": len(top),
            "series": top, "parsed": promql_to_dict(q),
        }

    # ── rate：每个资产 (最近值 - 窗口起点值) / 窗口秒数 ──
    if agg == "rate":
        secs = _window_to_seconds(q.range_window or "5m") or 300
        series = []
        for aid, rs in by_asset.items():
            rs_sorted = sorted(rs, key=lambda x: x.timestamp)
            if len(rs_sorted) < 2:
                continue
            latest_v = rs_sorted[-1].value
            earliest_v = rs_sorted[0].value
            rate = (latest_v - earliest_v) / secs
            series.append({"asset_id": aid, "rate": round(rate, 6),
                           "latest": latest_v, "earliest": earliest_v})
        return {
            "mode": "promql", "promql": expr, "metric_name": q.metric_name,
            "aggregator": "rate", "window": q.range_window, "count": len(series),
            "series": series, "parsed": promql_to_dict(q),
        }

    # ── avg_over_time / max_over_time / min_over_time / sum_over_time：每个资产窗口内聚合 ──
    if agg in ("avg_over_time", "max_over_time", "min_over_time", "sum_over_time"):
        series = []
        op = agg.split("_")[0]  # avg / max / min / sum
        for aid, rs in by_asset.items():
            vals = [r.value for r in rs]
            if not vals:
                continue
            if op == "avg":
                v = sum(vals) / len(vals)
            elif op == "max":
                v = max(vals)
            elif op == "min":
                v = min(vals)
            else:
                v = sum(vals)
            series.append({"asset_id": aid, "value": round(v, 4), "unit": rs[0].unit,
                           "sample_count": len(vals)})
        return {
            "mode": "promql", "promql": expr, "metric_name": q.metric_name,
            "aggregator": agg, "window": q.range_window, "count": len(series),
            "series": series, "parsed": promql_to_dict(q),
        }

    return {"mode": "promql", "error": f"不支持的聚合: {agg}", "raw": expr, "parsed": promql_to_dict(q)}


def _window_to_seconds(window: str) -> int:
    """'5m' / '1h' → 秒数。无效返回 0。"""
    import re
    m = re.match(r'^(\d+)([smhdw])$', window.strip())
    if not m:
        return 0
    n, unit = int(m.group(1)), m.group(2)
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]


def _compute_range_aggregation(by_asset: Dict[int, list], inner_agg: str, window: Optional[str]) -> list:
    """对按资产分组的 records 执行 range 聚合（rate / avg_over_time / max_over_time / min_over_time / sum_over_time）。
    返回 [{asset_id, value/rate, ...}] 列表。"""
    secs = _window_to_seconds(window or "5m") or 300
    series = []
    for aid, rs in by_asset.items():
        rs_sorted = sorted(rs, key=lambda x: x.timestamp)
        if not rs_sorted:
            continue
        if inner_agg == "rate":
            if len(rs_sorted) < 2:
                continue
            latest_v = rs_sorted[-1].value
            earliest_v = rs_sorted[0].value
            rate = (latest_v - earliest_v) / secs
            series.append({"asset_id": aid, "rate": round(rate, 6),
                           "latest": latest_v, "earliest": earliest_v, "value": round(rate, 6)})
        elif inner_agg in ("avg_over_time", "max_over_time", "min_over_time", "sum_over_time"):
            vals = [r.value for r in rs_sorted]
            op = inner_agg.split("_")[0]
            if op == "avg":
                v = sum(vals) / len(vals) if vals else 0
            elif op == "max":
                v = max(vals) if vals else 0
            elif op == "min":
                v = min(vals) if vals else 0
            else:
                v = sum(vals)
            series.append({"asset_id": aid, "value": round(v, 4), "unit": rs_sorted[0].unit,
                           "sample_count": len(vals)})
    return series
# ─── Incident Tools ────────────────────────────────────────────

@register_mcp_tool(
    name="query_incidents",
    description="查询故障单列表",
    input_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "故障单状态: open, closed"},
            "limit": {"type": "integer", "description": "返回数量限制", "default": 10},
        },
    },
    risk_level="read_only",
    display_name="查询故障单",
    location="cloud",
    category="incident",
)
def query_incidents(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        query = db.query(Incident)
        if kwargs.get("status"):
            query = query.filter(Incident.status == kwargs["status"])
        limit = kwargs.get("limit", 10)
        incidents = query.order_by(Incident.created_at.desc()).limit(limit).all()
        return {
            "count": len(incidents),
            "incidents": [
                {
                    "id": i.id,
                    "title": i.title,
                    "severity": i.severity,
                    "status": i.status,
                    "created_at": str(i.created_at),
                }
                for i in incidents
            ],
        }
    finally:
        if close_db:
            db.close()
# ─── Change Record Tools ────────────────────────────────────────

@register_mcp_tool(
    name="query_change_records",
    description="查询资产变更记录，支持按资产ID和时间范围筛选。变更记录包括配置变更、部署、健康状态变化等。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "资产 ID（可选，查询该资产的变更记录）"},
            "hours": {"type": "integer", "description": "查询最近多少小时的变更记录（可选，默认查所有）"},
            "limit": {"type": "integer", "description": "返回数量限制", "default": 50},
        },
    },
    risk_level="read_only",
    display_name="查询变更记录",
    location="cloud",
    category="change",
)
def query_change_records(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    from app.models import AssetChangeLog
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        query = db.query(AssetChangeLog)
        if kwargs.get("asset_id"):
            query = query.filter(AssetChangeLog.asset_id == kwargs["asset_id"])
        if kwargs.get("hours"):
            cutoff = datetime.now() - timedelta(hours=int(kwargs["hours"]))
            query = query.filter(AssetChangeLog.created_at >= cutoff)
        limit = kwargs.get("limit", 50)
        logs = query.order_by(AssetChangeLog.created_at.desc()).limit(limit).all()
        return {
            "count": len(logs),
            "changes": [
                {
                    "id": lg.id,
                    "asset_id": lg.asset_id,
                    "asset_name": lg.asset_name,
                    "field": lg.field,
                    "old_value": lg.old_value,
                    "new_value": lg.new_value,
                    "operator": lg.operator,
                    "created_at": str(lg.created_at),
                }
                for lg in logs
            ],
        }
    finally:
        if close_db:
            db.close()
# ─── K8s Tools ─────────────────────────────────────────────────

@register_mcp_tool(
    name="list_k8s_pods",
    description="列出 K8s Pod 列表",
    input_schema={
        "type": "object",
        "properties": {
            "cluster": {"type": "string", "description": "K8s 集群名称"},
            "namespace": {"type": "string", "description": "命名空间"},
            "limit": {"type": "integer", "description": "返回数量限制", "default": 20},
        },
    },
    risk_level="read_only",
    display_name="K8s Pod 列表",
    location="cloud",
    category="k8s",
)
def list_k8s_pods(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        query = db.query(Asset).filter(Asset.ci_type == "pod")
        if kwargs.get("cluster"):
            query = query.filter(Asset.k8s_cluster == kwargs["cluster"])
        if kwargs.get("namespace"):
            query = query.filter(Asset.name.ilike(f"{kwargs['namespace']}%"))
        limit = kwargs.get("limit", 20)
        pods = query.order_by(Asset.name).limit(limit).all()
        return {
            "count": len(pods),
            "pods": [
                {
                    "id": p.id,
                    "name": p.name,
                    "ip": p.ip,
                    "status": p.status,
                    "cluster": p.k8s_cluster,
                    "tags": p.tags,
                }
                for p in pods
            ],
        }
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="query_k8s_events",
    description="查询 K8s 集群事件",
    input_schema={
        "type": "object",
        "properties": {
            "cluster": {"type": "string", "description": "K8s 集群名称"},
            "severity": {"type": "string", "description": "级别: warning, error, normal"},
            "limit": {"type": "integer", "description": "返回数量限制", "default": 20},
        },
    },
    risk_level="read_only",
    display_name="查询 K8s 事件",
    location="cloud",
    category="k8s",
)
def query_k8s_events(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        query = db.query(K8sEvent)
        if kwargs.get("cluster"):
            query = query.filter(K8sEvent.cluster == kwargs["cluster"])
        if kwargs.get("severity"):
            query = query.filter(K8sEvent.severity == kwargs["severity"])
        limit = kwargs.get("limit", 20)
        events = query.order_by(K8sEvent.created_at.desc()).limit(limit).all()
        return {
            "count": len(events),
            "events": [
                {
                    "id": e.id,
                    "type": e.kind,
                    "reason": e.reason,
                    "message": e.message,
                    "namespace": e.namespace,
                    "name": e.name,
                    "severity": e.severity,
                    "cluster": e.cluster,
                    "count": e.count,
                    "last_seen_at": str(e.last_seen_at) if e.last_seen_at else None,
                    "created_at": str(e.created_at),
                }
                for e in events
            ],
        }
    finally:
        if close_db:
            db.close()
