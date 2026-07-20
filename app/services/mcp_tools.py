import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import Alert, AlertRule, Asset, ChatSession, MetricRecord, K8sEvent, Incident, KnowledgeBase
from app.services.mcp_registry import register_mcp_tool, get_internal_tools, get_mcp_tool
from app.services import remediation_service, alert_service, incident_service, asset_service, rag_service
from app.routers.observability_correlation import run_correlation_analysis, format_correlation_for_llm
from app.services.promql_parser import parse_promql, promql_to_dict


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
            except ValueError:
                pass
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


# ─── Knowledge Tools ───────────────────────────────────────────

@register_mcp_tool(
    name="generate_knowledge_from_incident",
    description="从已解决的故障单生成知识草稿并提交审批。当用户要求'把这次故障记录到知识库'、'生成知识沉淀'时调用此工具。知识草稿包含故障现象、根因分析、解决方案、标签。草稿状态为 pending 需人工审批。",
    input_schema={
        "type": "object",
        "properties": {
            "incident_id": {"type": "integer", "description": "已解决的故障单 ID"},
        },
        "required": ["incident_id"],
    },
    risk_level="medium",
    display_name="知识沉淀·故障单",
    expose_to_llm=True,
    location="cloud",
    category="knowledge",
)
def generate_knowledge_from_incident(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        from app.services.knowledge_autogen_service import generate_from_incident
        incident_id = kwargs.get("incident_id")
        if not incident_id:
            return {"error": "缺少必填参数: incident_id"}
        result = generate_from_incident(incident_id, db)
        if result.get("ok"):
            return {
                "status": "success",
                "draft_id": result["draft_id"],
                "title": result["title"],
                "message": f"知识草稿已生成（ID: {result['draft_id']}），标题：{result['title']}，状态：待审批",
            }
        return {"error": result.get("error", "生成失败")}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="generate_knowledge_from_alert",
    description="从已解决的告警生成知识草稿。适用场景：告警处理后用户要求'把这个告警记下来'。知识草稿包含告警指标、根因、解决方案。草稿状态为 pending 需人工审批。",
    input_schema={
        "type": "object",
        "properties": {
            "alert_id": {"type": "integer", "description": "已解决的告警 ID"},
        },
        "required": ["alert_id"],
    },
    risk_level="medium",
    display_name="知识沉淀·告警",
    expose_to_llm=True,
    location="cloud",
    category="knowledge",
)
def generate_knowledge_from_alert(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        from app.services.knowledge_autogen_service import generate_draft
        alert_id = kwargs.get("alert_id")
        if not alert_id:
            return {"error": "缺少必填参数: alert_id"}
        result = generate_draft(alert_id, db)
        if result.get("ok"):
            return {
                "status": "success",
                "draft_id": result["draft_id"],
                "title": result["title"],
                "message": f"知识草稿已生成（ID: {result['draft_id']}），标题：{result['title']}，状态：待审批",
            }
        return {"error": result.get("error", "生成失败")}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="query_knowledge",
    description="查询运维知识库",
    input_schema={
        "type": "object",
        "properties": {
            "search": {"type": "string", "description": "搜索关键字"},
            "tag": {"type": "string", "description": "按标签筛选"},
            "limit": {"type": "integer", "description": "返回数量限制", "default": 10},
        },
    },
    risk_level="read_only",
    display_name="知识库检索",
    location="cloud",
    category="knowledge",
)
def query_knowledge(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        query = db.query(KnowledgeBase)
        if kwargs.get("search"):
            query = query.filter(KnowledgeBase.title.ilike(f"%{kwargs['search']}%"))
        if kwargs.get("tag"):
            query = query.filter(KnowledgeBase.tags.ilike(f"%{kwargs['tag']}%"))
        limit = kwargs.get("limit", 10)
        items = query.order_by(KnowledgeBase.created_at.desc()).limit(limit).all()
        return {
            "count": len(items),
            "items": [
                {
                    "id": k.id,
                    "title": k.title,
                    "symptom": k.symptom,
                    "solution": k.solution,
                    "tags": k.tags,
                    "severity": k.severity,
                }
                for k in items
            ],
        }
    finally:
        if close_db:
            db.close()


# ─── Knowledge RAG Tools (语义检索, 升级版 query_knowledge) ─────

@register_mcp_tool(
    name="query_knowledge_rag",
    description="语义检索运维知识库（RAG）。通过 TF-IDF 向量余弦相似度匹配历史故障处置经验、运维文档、告警归档案例，返回最相关的知识片段。比 query_knowledge 的关键词匹配更精准，支持语义近似查询。适用于：告警根因分析时查找历史处置经验、排查问题时搜索相关运维文档、新故障需要参考类似案例。",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索问题或故障描述，如'磁盘空间不足告警如何处理'、'nginx 服务无响应'"},
            "asset_type": {"type": "string", "description": "资产类型过滤（可选），如 server、pod、service"},
            "severity": {"type": "string", "description": "严重级别过滤（可选）：warning / critical / info"},
            "tags": {"type": "string", "description": "标签过滤（可选），如 disk、network"},
            "top_k": {"type": "integer", "description": "返回数量限制", "default": 5},
        },
        "required": ["query"],
    },
    risk_level="read_only",
    display_name="RAG 检索",
    location="cloud",
    category="knowledge",
)
def query_knowledge_rag(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        query = kwargs.get("query", "")
        if not query or not query.strip():
            return {"error": "检索内容不能为空"}
        top_k = kwargs.get("top_k", 5)
        results = rag_service.vector_search(
            db,
            query=query,
            top_k=min(int(top_k), 20),
            asset_type=kwargs.get("asset_type") or None,
            severity=kwargs.get("severity") or None,
            tags=kwargs.get("tags") or None,
        )
        return {
            "count": len(results),
            "query": query,
            "items": results,
        }
    finally:
        if close_db:
            db.close()


# ─── Runbook Tools (操作流程检索) ──────────────────────────────

@register_mcp_tool(
    name="query_runbook",
    description="检索运维操作流程（Runbook）。通过标题、症状、标签匹配标准操作流程文档，返回操作步骤、诊断方法。适用于：告警处置时查找标准操作流程、需要执行具体操作步骤时参考、故障修复时按步骤执行。",
    input_schema={
        "type": "object",
        "properties": {
            "search": {"type": "string", "description": "搜索关键字，匹配标题、症状、诊断、步骤"},
            "category": {"type": "string", "description": "分类筛选，如 运维、网络、数据库"},
            "asset_type": {"type": "string", "description": "资产类型筛选，如 server、database、pod"},
            "limit": {"type": "integer", "description": "返回数量限制", "default": 5},
        },
    },
    risk_level="read_only",
    display_name="Runbook 检索",
    location="cloud",
    category="knowledge",
)
def query_runbook(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        from app.models import Runbook
        query = db.query(Runbook)
        if kwargs.get("search"):
            search = kwargs["search"]
            from sqlalchemy import or_
            query = query.filter(or_(
                Runbook.title.ilike(f"%{search}%"),
                Runbook.symptom.ilike(f"%{search}%"),
                Runbook.diagnosis.ilike(f"%{search}%"),
                Runbook.steps.ilike(f"%{search}%"),
                Runbook.tags.ilike(f"%{search}%"),
            ))
        if kwargs.get("category"):
            query = query.filter(Runbook.category == kwargs["category"])
        if kwargs.get("asset_type"):
            query = query.filter(Runbook.asset_type == kwargs["asset_type"])
        limit = kwargs.get("limit", 5)
        items = query.order_by(Runbook.created_at.desc()).limit(limit).all()
        return {
            "count": len(items),
            "items": [
                {
                    "id": r.id,
                    "title": r.title,
                    "category": r.category,
                    "symptom": r.symptom,
                    "diagnosis": r.diagnosis,
                    "steps": r.steps,
                    "tags": r.tags,
                    "severity": r.severity,
                    "asset_type": r.asset_type,
                }
                for r in items
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


# ─── Analysis Tools ────────────────────────────────────────────

@register_mcp_tool(
    name="analyze_incident_rca",
    description="分析故障单的根因",
    input_schema={
        "type": "object",
        "properties": {
            "incident_id": {"type": "integer", "description": "故障单 ID"},
        },
        "required": ["incident_id"],
    },
    risk_level="read_only",
    display_name="RCA 根因分析",
    location="cloud",
    category="rca",
)
def analyze_incident_rca(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    from app.services.rca_service import analyze_incident
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        incident_id = kwargs.get("incident_id")
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if not incident:
            return {"error": "故障单未找到"}
        result = analyze_incident(db, incident_id)
        return result
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="query_correlation_analysis",
    description="查询多维度可观测性关联分析结果。同时分析告警、指标异常(Z-Score)、日志异常(K8s Events)、链路追踪(慢调用+错误率)四个信号维度，按资产加权评分聚合。适用于：系统出现异常时快速了解全局状态、告警风暴时定位根因资产、故障复盘时查看多信号关联关系。返回关联分析概览+告警列表+指标异常+日志异常+链路追踪+资产评分+RCA预判建议。支持按时间范围、服务名、资产ID筛选。",
    input_schema={
        "type": "object",
        "properties": {
            "hours": {"type": "integer", "description": "分析时间范围（最近多少小时）", "default": 1},
            "service": {"type": "string", "description": "服务名过滤（可选，模糊匹配）"},
            "asset_id": {"type": "integer", "description": "资产 ID 过滤（可选）"},
        },
    },
    risk_level="read_only",
    display_name="关联分析",
    location="cloud",
    category="rca",
)
def query_correlation_analysis(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        hours = int(kwargs.get("hours", 1))
        service = kwargs.get("service", "")
        asset_id = int(kwargs.get("asset_id", 0))
        data = run_correlation_analysis(db, hours, service, asset_id)
        formatted = format_correlation_for_llm(data)
        return {
            "summary": data.get("summary", {}),
            "alert_count": len(data.get("alerts", [])),
            "metric_anomaly_count": len(data.get("metric_anomalies", [])),
            "log_anomaly_count": len(data.get("log_anomalies", [])),
            "trace_error_rate_pct": data.get("trace_anomalies", {}).get("error_rate_pct", 0),
            "correlated_asset_count": data.get("summary", {}).get("correlated_assets", 0),
            "change_record_count": len(data.get("change_records", [])),
            "rca_suggestions": data.get("rca_suggestions", []),
            "detail": formatted,
        }
    finally:
        if close_db:
            db.close()


# ─── Execute Tools (待确认动作执行链路, expose_to_llm=False) ───
# 以下 execute_* 工具供 confirm_pending_action 通过 call_mcp_tool 调用,
# 不暴露给 LLM (expose_to_llm=False), 防止绕过人工确认直接执行高危操作.
#
# 设计约定 (与 call_mcp_tool 包装语义对齐):
#   - 业务成功 -> 返回 {"status":"success","message":"...","data":...}
#     call_mcp_tool 会包成 {"status":"success","result":{...}}, confirm 判定成功.
#   - 业务失败/异常 -> 抛异常 (ValueError/RuntimeError),
#     call_mcp_tool 捕获后返回 {"status":"error","message":...}, confirm 判定失败.
#   - 切勿在 handler 内返回 {"status":"error",...} dict, 否则会被外层误包为 success.


@register_mcp_tool(
    name="execute_restart_service",
    description="通过 SSH 远程重启指定资产主机上的服务 (高危, 需人工确认). 必须指定 asset_id 指向 CMDB 中的资产记录",
    input_schema={
        "type": "object",
        "properties": {
            "service": {"type": "string", "description": "服务名称, 如 nginx、mysql"},
            "asset_id": {"type": "integer", "description": "目标资产 ID (CMDB 资产记录), 系统将通过该资产的 SSH 连接配置远程执行"},
        },
        "required": ["service", "asset_id"],
    },
    risk_level="high",
    display_name="重启服务",
    expose_to_llm=False,
    location="edge",
    category="execute_host",
)
def execute_restart_service(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        service = kwargs.get("service")
        asset_id = kwargs.get("asset_id")
        pending_action_id = kwargs.get("_pending_action_id")
        if not service:
            raise ValueError("缺少必填参数: service")
        if asset_id is None:
            raise ValueError("缺少必填参数: asset_id")
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            raise ValueError(f"资产 id={asset_id} 不存在")
        if asset.status != "online":
            raise ValueError(f"资产 {asset.name} 当前状态为 {asset.status}，仅 online 资产可远程执行")
        if asset.connection_type != "ssh":
            raise ValueError(f"资产 {asset.name} 连接类型为 {asset.connection_type}，仅 ssh 类型支持远程执行。对于数据库(database)类型资产，请使用 mysql action_type 通过 SQL 操作。")
        # 异步路径：有 pending_action_id（来自 propose → confirm 链路）则走 BackgroundJob
        if pending_action_id:
            from app.services.background_task import submit_restart_job
            job_id = submit_restart_job(service=service, asset_id=int(asset_id),
                                      pending_action_id=pending_action_id)
            return {
                "status": "executing",
                "message": f"重启任务已提交，job_id={job_id}",
                "data": {"job_id": job_id, "service": service, "asset_id": asset_id, "ip": asset.ip},
            }
        # 同步路径：兼容其他调用方
        success, message = remediation_service.execute_action("restart", {"service": service}, asset)
        if not success:
            raise RuntimeError(message)
        return {"status": "success", "message": message, "data": {"service": service, "asset_id": asset.id, "ip": asset.ip}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_clean_disk",
    description="通过 SSH 远程清理指定资产主机上某路径的磁盘空间 (高危, 需人工确认). 必须指定 asset_id",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "待清理路径, 如 /tmp、/var/log"},
            "asset_id": {"type": "integer", "description": "目标资产 ID (CMDB 资产记录)"},
        },
        "required": ["path", "asset_id"],
    },
    risk_level="high",
    display_name="清理磁盘",
    expose_to_llm=False,
    location="edge",
    category="execute_host",
)
def execute_clean_disk(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        path = kwargs.get("path")
        asset_id = kwargs.get("asset_id")
        if not path:
            raise ValueError("缺少必填参数: path")
        if asset_id is None:
            raise ValueError("缺少必填参数: asset_id")
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            raise ValueError(f"资产 id={asset_id} 不存在")
        if asset.status != "online":
            raise ValueError(f"资产 {asset.name} 当前状态为 {asset.status}，仅 online 资产可远程执行")
        if asset.connection_type != "ssh":
            raise ValueError(f"资产 {asset.name} 连接类型为 {asset.connection_type}，仅 ssh 类型支持远程执行。对于数据库(database)类型资产，请使用 mysql action_type 通过 SQL 操作。")
        success, message = remediation_service.execute_action("clean", {"path": path}, asset)
        if not success:
            raise RuntimeError(message)
        return {"status": "success", "message": message, "data": {"path": path, "asset_id": asset.id, "ip": asset.ip}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_run_script",
    description="通过 SSH 在指定资产主机上执行脚本 (极危, 需人工确认). 必须指定 asset_id",
    input_schema={
        "type": "object",
        "properties": {
            "script": {"type": "string", "description": "脚本在远程主机上的绝对路径, 如 /opt/scripts/fix.sh"},
            "asset_id": {"type": "integer", "description": "目标资产 ID (CMDB 资产记录)"},
        },
        "required": ["script", "asset_id"],
    },
    risk_level="critical",
    display_name="执行脚本",
    expose_to_llm=False,
    location="edge",
    category="execute_host",
)
def execute_run_script(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        script = kwargs.get("script")
        asset_id = kwargs.get("asset_id")
        pending_action_id = kwargs.get("_pending_action_id")
        if not script:
            raise ValueError("缺少必填参数: script")
        if asset_id is None:
            raise ValueError("缺少必填参数: asset_id")
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            raise ValueError(f"资产 id={asset_id} 不存在")
        if asset.status != "online":
            raise ValueError(f"资产 {asset.name} 当前状态为 {asset.status}，仅 online 资产可远程执行")
        if asset.connection_type != "ssh":
            raise ValueError(f"资产 {asset.name} 连接类型为 {asset.connection_type}，仅 ssh 类型支持远程执行。对于数据库(database)类型资产，请使用 mysql action_type 通过 SQL 操作。")
        # 异步路径
        if pending_action_id:
            from app.services.background_task import submit_script_job
            job_id = submit_script_job(script=script, asset_id=int(asset_id),
                                   pending_action_id=pending_action_id)
            return {
                "status": "executing",
                "message": f"脚本执行任务已提交，job_id={job_id}",
                "data": {"job_id": job_id, "script": script, "asset_id": asset_id, "ip": asset.ip},
            }
        # 同步路径
        success, output = remediation_service.execute_action("script", {"script": script}, asset)
        if not success:
            raise RuntimeError(output)
        return {"status": "success", "message": output, "data": {"script": script, "asset_id": asset.id, "ip": asset.ip}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_run_command",
    description="通过 SSH 在指定资产主机上执行任意命令 (极危, 需人工确认). 适用于诊断命令如 ps/df/free/top/grep/cat 等. 危险命令(rm -rf /、mkfs、dd、shutdown、reboot 等)会被黑名单拦截. 必须指定 asset_id",
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令, 如 'ps aux | grep nginx'、'df -h'、'free -m'"},
            "asset_id": {"type": "integer", "description": "目标资产 ID (CMDB 资产记录)"},
        },
        "required": ["command", "asset_id"],
    },
    risk_level="critical",
    display_name="执行命令",
    expose_to_llm=False,
    location="edge",
    category="execute_host",
)
def execute_run_command(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        command = kwargs.get("command")
        asset_id = kwargs.get("asset_id")
        if not command:
            raise ValueError("缺少必填参数: command")
        if asset_id is None:
            raise ValueError("缺少必填参数: asset_id")
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            raise ValueError(f"资产 id={asset_id} 不存在")
        if asset.status != "online":
            raise ValueError(f"资产 {asset.name} 当前状态为 {asset.status}，仅 online 资产可远程执行")
        if asset.connection_type != "ssh":
            raise ValueError(f"资产 {asset.name} 连接类型为 {asset.connection_type}，仅 ssh 类型支持远程执行。对于数据库(database)类型资产，请使用 mysql action_type 通过 SQL 操作。")
        success, output = remediation_service.execute_action("run_command", {"command": command}, asset)
        if not success:
            raise RuntimeError(output)
        return {"status": "success", "message": output, "data": {"command": command, "asset_id": asset.id, "ip": asset.ip}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_acknowledge_alert",
    description="确认告警 (标记为已处理)",
    input_schema={
        "type": "object",
        "properties": {
            "alert_id": {"type": "integer", "description": "告警 ID"},
        },
        "required": ["alert_id"],
    },
    risk_level="low",
    display_name="确认告警",
    expose_to_llm=False,
    location="cloud",
    category="alert",
)
def execute_acknowledge_alert(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        alert_id = kwargs.get("alert_id")
        if alert_id is None:
            raise ValueError("缺少必填参数: alert_id")
        alert = alert_service.acknowledge_alert(db, int(alert_id))
        if not alert:
            raise ValueError(f"告警 {alert_id} 未找到")
        return {"status": "success", "message": f"告警 {alert_id} 已确认", "data": {"alert_id": alert.id, "status": alert.status}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_resolve_alert",
    description="解决告警 (标记为已解决)",
    input_schema={
        "type": "object",
        "properties": {
            "alert_id": {"type": "integer", "description": "告警 ID"},
        },
        "required": ["alert_id"],
    },
    risk_level="low",
    display_name="解决告警",
    expose_to_llm=False,
    location="cloud",
    category="alert",
)
def execute_resolve_alert(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        alert_id = kwargs.get("alert_id")
        if alert_id is None:
            raise ValueError("缺少必填参数: alert_id")
        alert = alert_service.resolve_alert(db, int(alert_id))
        if not alert:
            raise ValueError(f"告警 {alert_id} 未找到")
        return {"status": "success", "message": f"告警 {alert_id} 已解决", "data": {"alert_id": alert.id, "status": alert.status}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_resolve_incident",
    description="解决故障单 (标记为已解决)",
    input_schema={
        "type": "object",
        "properties": {
            "incident_id": {"type": "integer", "description": "故障单 ID"},
        },
        "required": ["incident_id"],
    },
    risk_level="low",
    display_name="解决故障单",
    expose_to_llm=False,
    location="cloud",
    category="incident",
)
def execute_resolve_incident(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        incident_id = kwargs.get("incident_id")
        if incident_id is None:
            raise ValueError("缺少必填参数: incident_id")
        incident = incident_service.resolve_incident(db, int(incident_id))
        if not incident:
            raise ValueError(f"故障单 {incident_id} 未找到")
        return {"status": "success", "message": f"故障单 {incident_id} 已解决", "data": {"incident_id": incident.id, "status": incident.status}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_silence_alert",
    description="静默告警规则指定时长 (抑制告警通知)",
    input_schema={
        "type": "object",
        "properties": {
            "rule_id": {"type": "integer", "description": "告警规则 ID"},
            "minutes": {"type": "integer", "description": "静默时长 (分钟)"},
            "reason": {"type": "string", "description": "静默原因"},
        },
        "required": ["rule_id", "minutes"],
    },
    risk_level="medium",
    display_name="静默告警",
    expose_to_llm=False,
    location="cloud",
    category="alert",
)
def execute_silence_alert(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        rule_id = kwargs.get("rule_id")
        minutes = kwargs.get("minutes")
        reason = kwargs.get("reason", "")
        if rule_id is None or minutes is None:
            raise ValueError("缺少必填参数: rule_id, minutes")
        silence = alert_service.create_silence(db, int(rule_id), int(minutes), reason)
        return {"status": "success", "message": f"规则 {rule_id} 已静默 {minutes} 分钟", "data": {"silence_id": silence.id, "rule_id": silence.rule_id, "expires_at": str(silence.expires_at)}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_create_alert_rule",
    description="创建告警规则",
    input_schema={
        "type": "object",
        "properties": {
            "data": {
                "type": "object",
                "description": "告警规则数据",
                "properties": {
                    "name": {"type": "string", "description": "规则名称"},
                    "metric_name": {"type": "string", "description": "指标名称, 如 cpu_usage"},
                    "condition": {"type": "string", "description": "比较条件: gt (大于) / lt (小于)"},
                    "threshold": {"type": "number", "description": "阈值"},
                    "severity": {"type": "string", "description": "严重级别: warning / critical"},
                    "enabled": {"type": "boolean", "description": "是否启用"},
                },
                "required": ["name", "metric_name", "condition", "threshold"],
            },
        },
        "required": ["data"],
    },
    risk_level="medium",
    display_name="创建告警规则",
    expose_to_llm=False,
    location="cloud",
    category="alert",
)
def execute_create_alert_rule(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        data = kwargs.get("data")
        if not data:
            raise ValueError("缺少必填参数: data")
        rule = alert_service.create_rule(db, data)
        return {"status": "success", "message": f"告警规则 {rule.name} 已创建", "data": {"rule_id": rule.id, "name": rule.name}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_update_alert_rule",
    description="更新告警规则",
    input_schema={
        "type": "object",
        "properties": {
            "rule_id": {"type": "integer", "description": "告警规则 ID"},
            "data": {
                "type": "object",
                "description": "待更新的规则字段",
                "properties": {
                    "name": {"type": "string", "description": "规则名称"},
                    "metric_name": {"type": "string", "description": "指标名称"},
                    "condition": {"type": "string", "description": "比较条件: gt / lt"},
                    "threshold": {"type": "number", "description": "阈值"},
                    "severity": {"type": "string", "description": "严重级别"},
                    "enabled": {"type": "boolean", "description": "是否启用"},
                },
            },
        },
        "required": ["rule_id", "data"],
    },
    risk_level="medium",
    display_name="更新告警规则",
    expose_to_llm=False,
    location="cloud",
    category="alert",
)
def execute_update_alert_rule(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        rule_id = kwargs.get("rule_id")
        data = kwargs.get("data")
        if rule_id is None or not data:
            raise ValueError("缺少必填参数: rule_id, data")
        rule = alert_service.update_rule(db, int(rule_id), data)
        if not rule:
            raise ValueError(f"告警规则 {rule_id} 未找到")
        return {"status": "success", "message": f"告警规则 {rule_id} 已更新", "data": {"rule_id": rule.id, "name": rule.name}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_delete_alert_rule",
    description="删除告警规则 (高危, 不可恢复)",
    input_schema={
        "type": "object",
        "properties": {
            "rule_id": {"type": "integer", "description": "告警规则 ID"},
        },
        "required": ["rule_id"],
    },
    risk_level="high",
    display_name="删除告警规则",
    expose_to_llm=False,
    location="cloud",
    category="alert",
)
def execute_delete_alert_rule(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        rule_id = kwargs.get("rule_id")
        if rule_id is None:
            raise ValueError("缺少必填参数: rule_id")
        deleted = alert_service.delete_rule(db, int(rule_id))
        if not deleted:
            raise ValueError(f"告警规则 {rule_id} 未找到")
        return {"status": "success", "message": f"告警规则 {rule_id} 已删除", "data": {"rule_id": int(rule_id)}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_create_asset",
    description="创建资产 (CMDB 资产录入)",
    input_schema={
        "type": "object",
        "properties": {
            "data": {
                "type": "object",
                "description": "资产数据",
                "properties": {
                    "name": {"type": "string", "description": "资产名称"},
                    "type": {"type": "string", "description": "资产类型"},
                    "ci_type": {"type": "string", "description": "CI 类型: server / pod / deployment / service / node / cluster"},
                    "ip": {"type": "string", "description": "IP 地址"},
                    "status": {"type": "string", "description": "状态: online / offline / warning"},
                    "tags": {"type": "string", "description": "标签 (逗号分隔)"},
                    "k8s_cluster": {"type": "string", "description": "K8s 集群名称"},
                    "connection_type": {"type": "string", "description": "连接类型: ssh"},
                    "connection_config": {"type": "string", "description": "连接配置 (JSON 字符串)"},
                },
                "required": ["name", "type"],
            },
        },
        "required": ["data"],
    },
    risk_level="medium",
    display_name="创建资产",
    expose_to_llm=False,
    location="cloud",
    category="asset",
)
def execute_create_asset(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        data = kwargs.get("data")
        if not data:
            raise ValueError("缺少必填参数: data")
        asset = asset_service.create_asset(db, data)
        return {"status": "success", "message": f"资产 {asset.name} 已创建", "data": {"asset_id": asset.id, "name": asset.name}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_update_asset",
    description="更新资产信息",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "资产 ID"},
            "data": {
                "type": "object",
                "description": "待更新的资产字段",
                "properties": {
                    "name": {"type": "string", "description": "资产名称"},
                    "type": {"type": "string", "description": "资产类型"},
                    "ci_type": {"type": "string", "description": "CI 类型"},
                    "ip": {"type": "string", "description": "IP 地址"},
                    "status": {"type": "string", "description": "状态"},
                    "tags": {"type": "string", "description": "标签"},
                    "k8s_cluster": {"type": "string", "description": "K8s 集群名称"},
                    "connection_type": {"type": "string", "description": "连接类型"},
                    "connection_config": {"type": "string", "description": "连接配置"},
                },
            },
        },
        "required": ["asset_id", "data"],
    },
    risk_level="medium",
    display_name="更新资产",
    expose_to_llm=False,
    location="cloud",
    category="asset",
)
def execute_update_asset(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        asset_id = kwargs.get("asset_id")
        data = kwargs.get("data")
        if asset_id is None or not data:
            raise ValueError("缺少必填参数: asset_id, data")
        asset = asset_service.update_asset(db, int(asset_id), data)
        if not asset:
            raise ValueError(f"资产 {asset_id} 未找到")
        return {"status": "success", "message": f"资产 {asset_id} 已更新", "data": {"asset_id": asset.id, "name": asset.name}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_delete_asset",
    description="删除资产 (高危, 不可恢复)",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "资产 ID"},
        },
        "required": ["asset_id"],
    },
    risk_level="high",
    display_name="删除资产",
    expose_to_llm=False,
    location="cloud",
    category="asset",
)
def execute_delete_asset(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        asset_id = kwargs.get("asset_id")
        if asset_id is None:
            raise ValueError("缺少必填参数: asset_id")
        deleted = asset_service.delete_asset(db, int(asset_id))
        if not deleted:
            raise ValueError(f"资产 {asset_id} 未找到")
        return {"status": "success", "message": f"资产 {asset_id} 已删除", "data": {"asset_id": int(asset_id)}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_probe_assets",
    description="批量探测所有资产的连接状态并更新",
    input_schema={
        "type": "object",
        "properties": {},
    },
    risk_level="low",
    display_name="探测资产",
    expose_to_llm=False,
    location="edge",
    category="asset",
)
def execute_probe_assets(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        changed = asset_service.probe_assets(db)
        return {"status": "success", "message": f"资产探测完成, {len(changed)} 个状态变更", "data": {"changed_count": len(changed), "changed": changed}}
    finally:
        if close_db:
            db.close()


# ─── Action Proposal Tools (建议工具, 暴露给 LLM 触发 PendingAction) ───
# list_executable_actions / propose_action 是 LLM 触发待确认动作的唯一入口:
#   - list_executable_actions: 枚举 execute_* 内部工具清单 (action_type/参数 schema/风险等级)
#   - propose_action: 提议运维动作, 返回 _pending_action 字段;
#     process_chat_message 检测该字段后创建 PendingAction, 形成人工确认闭环.
# execute_* 工具本身 expose_to_llm=False, LLM 无法直调, 必须经 propose_action 走确认.


def _action_type_from_tool_name(name: str) -> str:
    """execute_restart_service -> restart_service; 非 execute_ 前缀原样返回."""
    return name[8:] if name.startswith("execute_") else name


# 风险等级序数: 用于"只允许升级不允许降级"校验, 防止 LLM 把高危操作标为低危绕过"知情同意"
_RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


# ─── 诊断命令白名单: 用于 propose_action 强制 auto_confirm (方案B) ───
# 只读诊断命令的首词集合, 这些命令不改写磁盘/不修改系统状态/不影响业务.
# yum/apt/systemctl/docker/kubectl 等命令读写混杂 (yum install 写, yum list 读),
# 不纳入白名单, 由 LLM 自评 risk_level + auto_confirm.
# bash/sh 不纳入 (bash -c 'rm -rf /' 可执行任意命令, 风险不可控).
_READ_ONLY_COMMAND_PREFIXES = {
    "ps", "df", "free", "top", "grep", "egrep", "fgrep", "which", "whereis",
    "echo", "date", "ls", "ll", "cat", "head", "tail", "wc", "uname", "whoami",
    "id", "env", "printenv", "hostname", "ip", "ifconfig", "uptime", "who",
    "last", "find", "ss", "netstat", "lsof", "stat", "file", "du", "lsblk",
    "journalctl", "dmesg", "rpm", "nginx", "httpd", "test", "pwd", "basename",
    "dirname", "realpath", "readlink", "md5sum", "sha256sum", "cksum", "cut",
    "tr", "sort", "uniq", "awk", "sed",  # 注意: sed -i 是写操作, 由危险命令黑名单兜底
}


def _is_read_only_diagnostic_command(command: str) -> bool:
    """判断命令是否为只读诊断命令 (所有子命令首词都在白名单).

    用于 propose_action 强制 auto_confirm=true, 跳过用户确认.
    判定规则: 用管道/分号/逻辑与或分割成多个子命令, 每个子命令去掉 sudo 前缀后
    取首词, 全部在白名单才返回 True. 任一子命令首词不在白名单则返回 False.
    这样 `echo x | sudo rm` 会被拒绝 (rm 不在白名单), `ps aux | grep nginx` 会通过.
    """
    if not command or not isinstance(command, str):
        return False
    # 按 || && ; | 分割 (注意双字符操作符先匹配)
    parts = re.split(r'\|\||&&|;|\|', command)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if not tokens:
            continue
        # 去掉 sudo 前缀
        if tokens[0] == "sudo" and len(tokens) > 1:
            tokens = tokens[1:]
        first = tokens[0]
        if first not in _READ_ONLY_COMMAND_PREFIXES:
            return False
    return True


@register_mcp_tool(
    name="list_executable_actions",
    description="列出所有可提议执行的运维动作清单 (action_type、风险等级、参数 schema)。AI 助手在提议运维操作前应先调用此工具了解可用动作及其参数要求。",
    input_schema={
        "type": "object",
        "properties": {},
    },
    risk_level="read_only",
    display_name="可执行动作清单",
    expose_to_llm=True,
    location="cloud",
    category="propose",
)
def list_executable_actions(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    actions = [
        {
            "action_type": _action_type_from_tool_name(tool.name),
            "tool_name": tool.name,
            "description": tool.description,
            "risk_level": tool.risk_level,
            "input_schema": tool.input_schema,
        }
        for tool in get_internal_tools()
        if tool.name.startswith("execute_")
    ]
    return {"actions": actions}


@register_mcp_tool(
    name="propose_action",
    description="提议一个运维操作, 生成待确认动作供用户确认后执行。不直接执行任何操作, 仅创建待确认记录。AI 助手想执行运维操作时必须用此工具提议, 不能直接调用 execute_* 工具。",
    input_schema={
        "type": "object",
        "properties": {
            "action_type": {"type": "string", "description": "动作类型, 对应 execute_* 的后缀 (如 restart_service、acknowledge_alert), 必须是 list_executable_actions 返回的合法值"},
            "title": {"type": "string", "description": "动作标题, 展示给用户"},
            "payload": {"type": "object", "description": "执行参数, 将原样传给对应的 execute_* 工具"},
            "risk_level": {"type": "string", "description": "风险等级: low / medium / high / critical, 默认由 action_type 推断", "enum": ["low", "medium", "high", "critical"]},
            "reason": {"type": "string", "description": "提议原因"},
            "auto_confirm": {"type": "boolean", "description": "设为 true 时跳过用户确认直接执行（仅限低风险只读诊断命令如 ps/df/which/grep），写操作必须为 false 等待用户确认", "default": False},
        },
        "required": ["action_type", "title", "payload"],
    },
    risk_level="advisory",
    display_name="提议运维动作",
    expose_to_llm=True,
    location="cloud",
    category="propose",
)
def propose_action(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    action_type = kwargs.get("action_type")
    title = kwargs.get("title")
    payload = kwargs.get("payload")
    reason = kwargs.get("reason", "")
    user_risk = kwargs.get("risk_level")
    auto_confirm = kwargs.get("auto_confirm", False)

    # Fail Fast: 必填参数缺失立即抛错 (call_mcp_tool 捕获后包装为 error)
    if not action_type:
        raise ValueError("缺少必填参数: action_type")
    if not title:
        raise ValueError("缺少必填参数: title")
    if payload is None:
        raise ValueError("缺少必填参数: payload")
    # Fail Fast: payload 必须是 dict（_parse_text_tool_calls 中 json.loads 失败会回退原字符串，
    # 导致此处收到 str；对字符串做 `in` 会按子串匹配，行为异常，故入口立即拦截非 dict 类型）
    if not isinstance(payload, dict):
        raise ValueError(f"payload 必须是对象(dict), 收到 {type(payload).__name__}")

    # 自动剥离 execute_ 前缀: LLM 常把 "execute_run_command" 当作 action_type 传入
    if action_type.startswith("execute_"):
        action_type = action_type[len("execute_"):]

    # 校验 action_type 合法性 + 收集登记风险等级
    # 只纳入 execute_ 前缀工具, 防 confirm 拼接 execute_{action_type} 时工具名错配导致静默失败
    valid_actions: Dict[str, str] = {}  # action_type -> execute_* risk_level
    for tool in get_internal_tools():
        if not tool.name.startswith("execute_"):
            continue
        valid_actions[_action_type_from_tool_name(tool.name)] = tool.risk_level

    if action_type not in valid_actions:
        _valid_list = sorted(valid_actions.keys())
        raise ValueError(
            f"非法 action_type: '{action_type}'。合法值: {', '.join(_valid_list)}。"
            f"注意 action_type 不要加 execute_ 前缀（如用 run_command 而非 execute_run_command）"
        )

    # 风险等级: 只允许升级不允许降级 — 取 LLM 指定值与登记值中更高者
    # 防止 LLM 把高危操作 (如 execute_restart_service 登记为 high) 标为 low,
    # 让确认 UI 显示低危徽章诱导用户草率确认, 破坏"知情同意"安全控制
    if user_risk and user_risk not in _RISK_ORDER:
        raise ValueError(f"非法 risk_level: {user_risk}, 合法值: low/medium/high/critical")
    registered_risk = valid_actions[action_type]
    if user_risk and _RISK_ORDER[user_risk] > _RISK_ORDER[registered_risk]:
        risk_level = user_risk  # LLM 想升级, 允许 (升级无害, 用户会更谨慎)
    else:
        risk_level = registered_risk  # 用登记值 (防止降级)

    # 字段别名兼容: LLM 常把 "service" 误写成 "service_name" 等
    _FIELD_ALIASES = {
        "service": ["service_name"],
        "command": ["command_line", "cmd"],
    }
    for standard_field, aliases in _FIELD_ALIASES.items():
        if standard_field not in payload:
            for alias in aliases:
                if alias in payload:
                    payload[standard_field] = payload.pop(alias)
                    break

    # 方案B: 诊断命令白名单强制 auto_confirm=true
    # LLM 经常忘记设 auto_confirm 或对命令风险误判, 导致只读诊断命令 (ps/df/grep/find 等)
    # 仍卡在确认环节. 代码层判定: action_type=run_command 且命令在只读白名单时, 强制免确认.
    # 写操作 (install/restart/rm 等) 不受影响, 仍走用户确认流程.
    if action_type == "run_command":
        _cmd = payload.get("command", "")
        if _is_read_only_diagnostic_command(_cmd):
            auto_confirm = True

    # payload 必填字段校验: 文档承诺 payload 须符合对应 execute_* 工具参数 schema, 提前拦截畸形 payload
    # confirm 阶段仍会二次校验 (agent_service._validate_payload_schema), 此处为入口防御 + 文档与实现一致性
    exec_tool = get_mcp_tool(f"execute_{action_type}")
    if exec_tool and exec_tool.input_schema:
        required_fields = exec_tool.input_schema.get("required", []) or []
        missing = [f for f in required_fields if f not in payload]
        if missing:
            raise ValueError(f"payload 缺少必填字段: {', '.join(missing)}")

    # 返回 _pending_action: 字段与 process_chat_message 检测逻辑对齐
    # call_mcp_tool 包装后: tool_result["result"]["_pending_action"] 即此处的 _pending_action,
    # process_chat_message 据此创建 PendingAction (action_type/title/risk_level/payload).
    return {
        "status": "proposed",
        "_pending_action": {
            "action_type": action_type,
            "title": title,
            "payload": payload,
            "risk_level": risk_level,
            "reason": reason,
            "auto_confirm": auto_confirm,
        },
    }


# ─── SOP 工作流引擎 Tools (AI 触发多步运维剧本) ───
# list_workflow_templates: 枚举可用 SOP 模板 (read_only)
# propose_workflow: 创建 WorkflowRun + NodeRun 并立即执行只读节点, 写操作节点置 awaiting_confirm (advisory)
# 与 propose_action 的区别: propose_action 单步动作, propose_workflow 多步 DAG 编排
# 复用 execute_* 内部工具作为节点动作, 复用 PendingAction 确认理念 (节点 awaiting_confirm 状态)


@register_mcp_tool(
    name="list_workflow_templates",
    description="列出可用的 SOP 工作流模板。AI 助手处理多步骤运维任务时应先调用此工具了解可用剧本，再用 propose_workflow 触发。",
    input_schema={
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "按分类筛选: disk / service / scaling / healing / custom"},
            "only_enabled": {"type": "boolean", "description": "仅返回已启用模板", "default": True},
        },
    },
    risk_level="read_only",
    display_name="工作流模板",
    location="cloud",
    category="workflow",
)
def list_workflow_templates(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        from app.services import workflow_service
        category = kwargs.get("category") or None
        only_enabled = bool(kwargs.get("only_enabled", True))
        result = workflow_service.list_templates(db, category=category, only_enabled=only_enabled)
        templates = result.get("items", []) if isinstance(result, dict) else (result or [])
        return {
            "count": len(templates),
            "templates": [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "description": t["description"],
                    "category": t["category"],
                    "trigger_type": t["trigger_type"],
                    "risk_level": t["risk_level"],
                    "nodes_count": len(t.get("nodes", [])),
                    "enabled": t["enabled"],
                }
                for t in templates
            ],
        }
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="propose_workflow",
    description="提议执行一个 SOP 工作流。会立即创建工作流实例并自动执行只读步骤，写操作步骤会暂停等待用户在前端确认。AI 助手处理多步骤运维任务时应优先用此工具，而非逐步 propose_action。",
    input_schema={
        "type": "object",
        "properties": {
            "template_id": {"type": "integer", "description": "SOP 模板 ID（可选，无则需提供 nodes/edges）"},
            "title": {"type": "string", "description": "工作流标题"},
            "context": {"type": "object", "description": "运行时上下文（asset_id、告警信息等），用于渲染节点 payload 模板"},
            "nodes": {"type": "array", "description": "自定义节点（无 template_id 时必填），每项含 id/name/action_type/payload_template/requires_confirm/retry_count"},
            "edges": {"type": "array", "description": "自定义边（无 template_id 时必填），每项含 source/target"},
        },
        "required": ["title"],
    },
    risk_level="advisory",
    display_name="提议工作流",
    location="cloud",
    category="workflow",
)
def propose_workflow(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        from app.services import workflow_service
        template_id = kwargs.get("template_id")
        title = kwargs.get("title")
        context = kwargs.get("context") or {}
        custom_nodes = kwargs.get("nodes")
        custom_edges = kwargs.get("edges")

        if not title:
            raise ValueError("缺少必填参数: title")
        if not template_id and not custom_nodes:
            raise ValueError("必须提供 template_id 或自定义 nodes")

        run, err = workflow_service.start_workflow_run(
            db,
            template_id=template_id,
            title=title,
            context=context,
            trigger_source="ai",
            session_id=None,
            custom_nodes=custom_nodes,
            custom_edges=custom_edges,
        )
        if err:
            return {"status": "error", "message": err}

        run_data = workflow_service.get_run(db, run.id)
        node_summary = []
        awaiting = []
        for nr in run_data.get("node_runs", []):
            node_summary.append({"node_id": nr["node_id"], "name": nr["node_name"], "status": nr["status"], "requires_confirm": nr["requires_confirm"]})
            if nr["status"] == "awaiting_confirm":
                awaiting.append({"node_run_id": nr["id"], "node_id": nr["node_id"], "name": nr["node_name"]})

        return {
            "status": "created",
            "run_id": run.id,
            "title": run.title,
            "workflow_status": run.status,
            "node_count": len(node_summary),
            "awaiting_confirm_count": len(awaiting),
            "awaiting_confirm_nodes": awaiting,
            "message": f"工作流 #{run.id} 已创建，只读步骤自动执行中，{len(awaiting)} 个写操作步骤待确认",
            "_pending_workflow": {"run_id": run.id, "title": run.title},
        }
    finally:
        if close_db:
            db.close()


# ─── 智能体编排工作流 MCP 工具 (Coze 风格) ───
# list_agent_workflows: 枚举已发布的智能体工作流 (read_only)
# run_agent_workflow: 执行智能体工作流，AI 在画布编排的 LLM/知识库/工具/条件分支节点链 (advisory)


@register_mcp_tool(
    name="list_agent_workflows",
    description="列出可用的智能体编排工作流（Coze 风格可视化编排）。AI 助手处理复杂多步骤任务时可调用此工具了解可用智能体，再用 run_agent_workflow 触发。",
    input_schema={
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "按分类筛选: analysis / chatbot / healing / report / generic"},
            "only_enabled": {"type": "boolean", "description": "仅返回已启用工作流", "default": True},
        },
    },
    risk_level="read_only",
    display_name="Agent 工作流列表",
    location="cloud",
    category="workflow",
)
def list_agent_workflows(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        from app.services import agent_workflow_service
        category = kwargs.get("category") or None
        only_enabled = bool(kwargs.get("only_enabled", True))
        workflows = agent_workflow_service.list_workflows(db, category=category, only_enabled=only_enabled)
        return {
            "count": len(workflows),
            "workflows": [
                {
                    "id": w["id"],
                    "name": w["name"],
                    "description": w["description"],
                    "category": w["category"],
                    "trigger_type": w["trigger_type"],
                    "nodes_count": len(w.get("nodes", [])),
                    "inputs_schema": w.get("inputs_schema", []),
                }
                for w in workflows
            ],
        }
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="run_agent_workflow",
    description="执行一个智能体编排工作流。工作流会按画布编排的节点顺序执行（LLM 推理/知识库检索/工具调用/条件分支等），返回最终输出。AI 助手处理复杂多步骤推理任务时应优先用此工具。",
    input_schema={
        "type": "object",
        "properties": {
            "workflow_id": {"type": "integer", "description": "智能体工作流 ID"},
            "inputs": {"type": "object", "description": "工作流输入参数，对应 start 节点定义的 inputs schema"},
        },
        "required": ["workflow_id", "inputs"],
    },
    risk_level="advisory",
    display_name="运行 Agent 工作流",
    location="cloud",
    category="workflow",
)
def run_agent_workflow(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        from app.services import agent_workflow_service
        workflow_id = kwargs.get("workflow_id")
        inputs = kwargs.get("inputs") or {}

        if not workflow_id:
            raise ValueError("缺少必填参数: workflow_id")

        run, err = agent_workflow_service.start_workflow_run(
            db,
            workflow_id=workflow_id,
            inputs=inputs,
            trigger_source="ai",
            session_id=None,
        )
        if err:
            return {"status": "error", "message": err}

        run_data = agent_workflow_service.get_run(db, run.id)
        node_summary = []
        for nr in run_data.get("node_runs", []):
            node_summary.append({
                "node_id": nr["node_id"],
                "name": nr["node_name"],
                "type": nr["node_type"],
                "status": nr["status"],
            })

        return {
            "status": "completed" if run.status == "completed" else run.status,
            "run_id": run.id,
            "workflow_status": run.status,
            "outputs": run_data.get("outputs", {}),
            "node_count": len(node_summary),
            "nodes": node_summary,
            "error": run_data.get("error", ""),
            "message": f"智能体工作流 #{run.id} 执行完成，状态: {run.status}",
        }
    finally:
        if close_db:
            db.close()


# ─── 后台任务 Tools ──────────────────────────────────────────────

@register_mcp_tool(
    name="get_task_status",
    description="查询后台异步任务的最新状态（进度/结果/错误），LLM 应定期轮询此工具获取长耗时任务（如安装、部署）的执行进度",
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "后台任务 ID（由 propose_action 返回的 job_id）"},
        },
        "required": ["job_id"],
    },
    risk_level="read_only",
    display_name="任务状态",
    expose_to_llm=True,
    location="cloud",
    category="task",
)
def get_task_status(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    from app.services.background_task import get_background_job
    job_id = kwargs.get("job_id")
    if not job_id:
        raise ValueError("缺少必填参数: job_id")
    result = get_background_job(job_id)
    if not result:
        return {"error": f"任务 {job_id} 未找到"}
    return result


@register_mcp_tool(
    name="list_recent_tasks",
    description="列出最近执行的后台任务（当前会话），用于查看有哪些任务在后台运行或刚结束",
    input_schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "integer", "description": "会话 ID，不传则查所有"},
            "limit": {"type": "integer", "description": "返回数量上限", "default": 20},
        },
    },
    risk_level="read_only",
    display_name="最近任务",
    expose_to_llm=True,
    location="cloud",
    category="task",
)
def list_recent_tasks(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    from app.services.background_task import list_running_jobs
    session_id = kwargs.get("session_id")
    limit = kwargs.get("limit", 20)
    jobs = list_running_jobs(session_id=session_id, limit=limit)
    return {"tasks": jobs, "count": len(jobs)}


@register_mcp_tool(
    name="execute_install_package",
    description="在远程资产上异步安装软件包（支持 Elasticsearch/Nginx/MySQL 等），任务在后台执行不受 LLM 超时限制，通过 get_task_status 轮询进度。安装完成后自动返回最终结果",
    input_schema={
        "type": "object",
        "properties": {
            "package_name": {"type": "string", "description": "软件包名，如 elasticsearch、nginx、mysql"},
            "asset_id": {"type": "integer", "description": "目标资产 ID（CMDB 资产记录，必须为 online 状态且连接类型为 ssh）"},
            "version": {"type": "string", "description": "版本号，如 8.19.0（不传则默认安装可用版本）"},
            "install_type": {"type": "string", "description": "安装方式: package（系统包）/ binary（二进制tar.gz）/ docker，默认 binary"},
            "options": {
                "type": "object",
                "description": "高级选项",
                "properties": {
                    "os_type": {"type": "string", "description": "操作系统类型: auto / debian / rhel / alpine，默认 auto（自动检测）"},
                    "extra_packages": {"type": "array", "items": {"type": "string"}, "description": "额外需要安装的依赖包"},
                    "start_service": {"type": "boolean", "description": "安装后是否启动服务，默认 true"},
                    "open_ports": {"type": "array", "items": {"type": "integer"}, "description": "需要开放的端口"},
                },
            },
        },
        "required": ["package_name", "asset_id"],
    },
    risk_level="critical",
    display_name="安装软件包",
    expose_to_llm=False,  # 不直调，必须经 propose_action,
    location="edge",
    category="execute_host",
)
def execute_install_package(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        package_name = kwargs.get("package_name")
        asset_id = kwargs.get("asset_id")
        version = kwargs.get("version", "latest")
        install_type = kwargs.get("install_type", "binary")
        options = kwargs.get("options", {})

        if not package_name:
            raise ValueError("缺少必填参数: package_name")
        if asset_id is None:
            raise ValueError("缺少必填参数: asset_id")

        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            raise ValueError(f"资产 id={asset_id} 不存在")
        if asset.status != "online":
            raise ValueError(f"资产 {asset.name} 当前状态为 {asset.status}，仅 online 资产可操作")
        if asset.connection_type != "ssh":
            raise ValueError(f"资产 {asset.name} 连接类型为 {asset.connection_type}，仅 ssh 类型支持。对于数据库(database)类型资产，请使用 mysql action_type 通过 SQL 操作。")

        # 提交后台任务
        from app.services.background_task import submit_install_job
        job_id = submit_install_job(
            package_name=package_name,
            asset_id=int(asset_id),
            version=version,
            options={**options, "install_type": install_type},
            session_id=None,
            pending_action_id=None,
        )
        return {
            "status": "success",
            "message": f"安装任务已提交，job_id={job_id}",
            "data": {
                "job_id": job_id,
                "package": package_name,
                "asset_id": asset_id,
                "ip": asset.ip,
                "status": "pending",
                "hint": "使用 get_task_status(job_id=...) 轮询任务进度",
            },
        }
    finally:
        if close_db:
            db.close()


# ─── 日志查询 Tool ──────────────────────────────────────────────

@register_mcp_tool(
    name="query_logs",
    description="查询日志（支持多日志源：Elasticsearch 等），根据关键词/主机/级别/时间范围过滤日志",
    input_schema={
        "type": "object",
        "properties": {
            "source_id": {"type": "integer", "description": "数据源 ID（从 query_log_sources 查询可用数据源）"},
            "query": {"type": "string", "description": "搜索关键词（支持多字段匹配 message/host/service/level），如 error / nginx / 192.168.1"},
            "time_range": {"type": "string", "description": "时间范围: 15m / 1h / 6h / 24h / 7d，默认 1h"},
            "level": {"type": "string", "description": "日志级别过滤: error / warning / info（可选）"},
            "host": {"type": "string", "description": "主机名过滤（如 web-server-01）"},
            "limit": {"type": "integer", "description": "返回条数，默认 20，最大 200"},
        },
        "required": ["source_id"],
    },
    risk_level="read_only",
    display_name="查询日志",
    expose_to_llm=True,
    location="cloud",
    category="log",
)
def query_logs(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    from app.services.log_query_service import query_logs as _query_logs
    source_id = kwargs.get("source_id")
    query_str = kwargs.get("query", "*")
    time_range = kwargs.get("time_range", "1h")
    level = kwargs.get("level", "")
    host = kwargs.get("host", "")
    limit = kwargs.get("limit", 20)

    if not source_id:
        raise ValueError("缺少必填参数: source_id（请先调用 query_log_sources 获取可用数据源）")

    try:
        logs, total, error = _query_logs(
            source_id=int(source_id),
            query=query_str,
            time_range=time_range,
            level=level,
            host=host,
            limit=limit,
        )
    except Exception as e:
        raise ValueError(f"日志数据源 {source_id} 查询失败: {str(e)}（请检查数据源配置/网络连通性）")

    if error:
        # 错误路径必须 raise，让 call_mcp_tool 包装成 {"status":"error","message":...}
        # 否则返回 dict 会被外层当成 success，LLM 误以为查询成功但无日志
        # （真实场景：ES 不可达时 LLM 看到"成功但 logs=[]"，会下结论"无错误日志"，
        #  实际上是查询本身失败，可能误导根因分析）
        raise ValueError(error)

    return {
        "logs": logs,
        "total": total,
        "query": query_str,
        "time_range": time_range,
        "level": level,
        "host": host,
    }


@register_mcp_tool(
    name="query_log_sources",
    description="查询当前系统已配置的所有日志数据源，返回 id / name / type / endpoint，用于后续 query_logs 查询",
    input_schema={
        "type": "object",
        "properties": {},
    },
    risk_level="read_only",
    display_name="日志数据源",
    expose_to_llm=True,
    location="cloud",
    category="log",
)
def query_log_sources(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    from app.models import DataSource
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        sources = db.query(DataSource).filter(
            DataSource.type.in_(["elasticsearch"])
        ).all()
        return {
            "sources": [
                {
                    "id": s.id,
                    "name": s.name,
                    "type": s.type,
                    "endpoint": s.endpoint or "",
                    "enabled": bool(s.enabled),
                }
                for s in sources
            ],
            "count": len(sources),
        }
    finally:
        if close_db:
            db.close()


# ─── 链路追踪 Tool ─────────────────────────────────────

@register_mcp_tool(
    name="query_traces",
    description="查询分布式链路追踪（Trace），返回调用链路树，包含每个 Span 的服务/操作/耗时/状态，用于定位慢链路和错误根因",
    input_schema={
        "type": "object",
        "properties": {
            "trace_id": {"type": "string", "description": "链路 ID（可选，精确查单条）"},
            "service": {"type": "string", "description": "服务名过滤（如 api-gateway / payment-service）"},
            "status": {"type": "string", "description": "状态过滤: OK / ERROR / WARN"},
            "time_range": {"type": "string", "description": "时间范围: 15m / 1h / 6h / 24h / 7d，默认 1h"},
            "limit": {"type": "integer", "description": "返回条数，默认 20"},
        },
    },
    risk_level="read_only",
    display_name="查询链路",
    expose_to_llm=True,
    location="cloud",
    category="trace",
)
def query_traces(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    import json as _json
    from datetime import timedelta as _td
    from app.models import Span as _Span
    from sqlalchemy import func as _func, desc as _desc

    trace_id = kwargs.get("trace_id", "")
    service = kwargs.get("service", "")
    status_filter = kwargs.get("status", "")
    time_range = kwargs.get("time_range", "1h")
    limit = min(kwargs.get("limit", 20), 100)

    # 解析时间范围
    now = datetime.now()
    m = re.match(r"^(\d+)([mhd])$", time_range.strip())
    if m:
        num, unit = int(m.group(1)), m.group(2)
        delta = _td(minutes=num) if unit == "m" else (_td(hours=num) if unit == "h" else _td(days=num))
        since = now - delta
    else:
        since = now - _td(hours=1)

    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        # 构造子查询：每个 trace_id 最小的 start_time
        subq = (
            db.query(
                _Span.trace_id,
                _func.min(_Span.started_at).label("min_start")
            )
            .filter(_Span.started_at >= since)
            .group_by(_Span.trace_id)
            .subquery()
        )
        root_q = (
            db.query(_Span)
            .join(subq, _Span.trace_id == subq.c.trace_id)
            .filter(_Span.started_at == subq.c.min_start)
        )
        if trace_id:
            root_q = root_q.filter(_Span.trace_id == trace_id)
        if service:
            root_q = root_q.filter(_Span.service_name.ilike(f"%{service}%"))
        if status_filter:
            root_q = root_q.filter(_Span.status == status_filter)
        root_q = root_q.order_by(_desc(_Span.started_at)).limit(limit)

        traces = []
        for root in root_q.all():
            all_spans = (
                db.query(_Span)
                .filter(_Span.trace_id == root.trace_id)
                .order_by(_Span.started_at)
                .all()
            )
            spans_data = []
            for s in all_spans:
                tags = {}
                try:
                    tags = _json.loads(s.tags or "{}")
                except Exception:
                    pass
                spans_data.append({
                    "span_id": s.span_id or "",
                    "service": s.service_name or "",
                    "operation": s.operation_name or "",
                    "duration_ms": s.duration_ms or 0,
                    "status": s.status or "OK",
                    "parent_span_id": s.parent_span_id or "",
                    "start_time": s.started_at.isoformat() if s.started_at else "",
                })
            root_durations = [sp["duration_ms"] for sp in spans_data]
            root_duration = max(root_durations) if root_durations else 0
            traces.append({
                "trace_id": root.trace_id or "",
                "root_service": root.service_name or "",
                "root_operation": root.operation_name or "",
                "root_duration_ms": root_duration,
                "root_status": root.status or "OK",
                "root_start": root.started_at.isoformat() if root.started_at else "",
                "spans_count": len(all_spans),
                "spans": spans_data,
            })

        return {"traces": traces, "count": len(traces), "time_range": time_range}
    finally:
        if close_db:
            db.close()


# ─── MySQL Query Tool ─────────────────────────────────────

@register_mcp_tool(
    name="query_mysql",
    description="连接 MySQL 数据库执行 SQL 查询（仅支持 SELECT/DESC/SHOW 语句），返回查询结果。连接信息从资产 connection_config 中读取。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "资产 ID（从 assets 表）"},
            "sql": {"type": "string", "description": "SQL 查询语句（仅支持读操作：SELECT/SHOW/DESC/DESCRIBE）"},
            "limit": {"type": "integer", "description": "最大返回行数，默认 100"},
        },
        "required": ["asset_id", "sql"],
    },
    risk_level="medium",
    display_name="查询 MySQL",
    expose_to_llm=True,
    location="cloud",
    category="mysql",
)
def query_mysql(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    import pymysql
    import json as _json

    asset_id = kwargs.get("asset_id")
    sql = kwargs.get("sql", "").strip()
    limit = min(kwargs.get("limit", 100), 1000)

    if not asset_id:
        return {"error": "缺少必填参数: asset_id"}
    if not sql:
        return {"error": "缺少必填参数: sql"}

    # 只允许读操作
    safe_sql = sql.upper()
    allowed = ["SELECT", "SHOW", "DESC", "DESCRIBE", "EXPLAIN"]
    if not any(safe_sql.startswith(a) for a in allowed):
        return {"error": "只允许 SELECT/SHOW/DESC/DESCRIBE/EXPLAIN 语句"}

    close_db = False
    if db is None:
        db = _get_db()
        close_db = True

    try:
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            return {"error": f"资产 {asset_id} 不存在"}

        cfg = _json.loads(asset.connection_config) if asset.connection_config else {}
        host = cfg.get("db_host") or cfg.get("mysql_host") or asset.ip
        port = int(cfg.get("db_port") or cfg.get("mysql_port") or 3306)
        user = cfg.get("db_user") or cfg.get("mysql_user") or "root"
        password = cfg.get("db_password") or cfg.get("mysql_password") or ""
        database = cfg.get("db_name") or cfg.get("mysql_database") or ""

        try:
            conn = pymysql.connect(
                host=host, port=port, user=user, password=password,
                database=database, charset="utf8mb4",
                connect_timeout=10, read_timeout=30
            )
        except pymysql.Error as e:
            return {"error": f"MySQL 连接失败: {e}", "host": host, "port": port, "user": user}

        try:
            cur = conn.cursor()
            cur.execute(sql + (" LIMIT %d" % limit if limit else ""))
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            return {
                "columns": cols,
                "rows": [list(r) for r in rows],
                "row_count": len(rows),
                "sql": sql,
                "asset": {"id": asset.id, "name": asset.name, "ip": asset.ip},
            }
        finally:
            conn.close()
    finally:
        if close_db:
            db.close()


# ─── MySQL 权限安全检测 ─────────────────────────────────

@register_mcp_tool(
    name="check_mysql_permissions",
    description="检测 MySQL 账号的权限等级，评估 AI 连接该数据库的安全风险。用于新增数据库资产时自动检测，辅助判断是否允许 AI 使用。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "数据库资产 ID"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only",
    display_name="检查 MySQL 权限",
    expose_to_llm=True,
    location="cloud",
    category="mysql",
)
def check_mysql_permissions(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    import pymysql
    import json as _json

    asset_id = kwargs.get("asset_id")
    if not asset_id:
        return {"error": "缺少必填参数: asset_id"}

    close_db = False
    if db is None:
        db = _get_db()
        close_db = True

    try:
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            return {"error": f"资产 {asset_id} 不存在"}

        cfg = _json.loads(asset.connection_config) if asset.connection_config else {}
        host = cfg.get("db_host") or cfg.get("mysql_host") or asset.ip
        port = int(cfg.get("db_port") or cfg.get("mysql_port") or 3306)
        user = cfg.get("db_user") or cfg.get("mysql_user") or "root"
        password = cfg.get("db_password") or cfg.get("mysql_password") or ""
        database = cfg.get("db_name") or ""

        try:
            conn = pymysql.connect(
                host=host, port=port, user=user, password=password,
                database=database, charset="utf8mb4",
                connect_timeout=10, read_timeout=30
            )
        except pymysql.Error as e:
            return {"error": f"MySQL 连接失败: {e}", "host": host, "port": port, "user": user}

        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM mysql.user WHERE User=%s AND Host=%s", (user, "%" if user != "root" else "%"))
            privs = []
            is_super = False
            if cur.description:
                cols = [d[0] for d in cur.description]
                for row in cur.fetchall():
                    priv_map = dict(zip(cols, row))
                    for col, val in priv_map.items():
                        if val in (True, 1, "Y", "y"):
                            privs.append(col)

            if conn and database:
                try:
                    # SHOW GRANTS 不支持参数化绑定，先对用户名做白名单校验防注入
                    import re as _re
                    if not _re.match(r"^[A-Za-z0-9_\-.@ ]{1,64}$", user or ""):
                        grants = []
                    else:
                        _safe_user = (user or "").replace("'", "''")
                        cur.execute(f"SHOW GRANTS FOR '{_safe_user}'@'%'")
                        grants = [r[0] for r in cur.fetchall()]
                except Exception:
                    grants = []
            else:
                grants = []

            ddl_privs = [p for p in privs if p in ("Drop_priv", "Alter_priv", "Create_priv", "Index_priv", "References_priv")]
            dml_privs = [p for p in privs if p in ("Insert_priv", "Update_priv", "Delete_priv", "Execute_priv")]
            dcl_privs = [p for p in privs if p in ("Grant_priv", "Super_priv", "Shutdown_priv", "Process_priv", "File_priv")]
            read_privs = [p for p in privs if p in ("Select_priv", "Show_db_priv", "Show_view_priv", "Lock_tables_priv")]

            has_grant_option = "Grant_priv" in privs or any("GRANT OPTION" in g for g in grants)
            is_super_user = "Super_priv" in privs

            if has_grant_option or is_super_user or ddl_privs or "File_priv" in privs:
                risk_level = "high"
                risk_label = "🔴 高危"
                risk_desc = "该账号拥有极高危权限（DCL/DDL/文件操作/授权），AI 可能导致数据丢失或权限失控"
            elif dml_privs:
                risk_level = "medium"
                risk_label = "⚠️ 警告"
                risk_desc = "该账号拥有 DML 权限（INSERT/UPDATE/DELETE），AI 可修改业务数据"
            elif read_privs and not dml_privs and not ddl_privs:
                risk_level = "safe"
                risk_label = "✅ 安全"
                risk_desc = "该账号仅有读权限，AI 仅能查询无法修改数据"
            else:
                risk_level = "unknown"
                risk_label = "❓ 未知"
                risk_desc = "无法明确判定权限等级，建议人工确认"

            return {
                "asset_id": asset_id,
                "asset_name": asset.name,
                "asset_ip": host,
                "mysql_user": user,
                "risk_level": risk_level,
                "risk_label": risk_label,
                "risk_desc": risk_desc,
                "privileges": {
                    "read": read_privs,
                    "dml": dml_privs,
                    "ddl": ddl_privs,
                    "dcl": dcl_privs,
                },
                "has_grant_option": has_grant_option,
                "is_super_user": is_super_user,
                "grants": grants,
                "recommendation": "仅【✅ 安全】权限的数据库建议接入 AI 助手；其他权限等级请评估风险后决定",
            }
        finally:
            conn.close()
    finally:
        if close_db:
            db.close()


# ─── MySQL Write Tool ─────────────────────────────────────

@register_mcp_tool(
    name="execute_mysql",
    description="通过资产记录的 MySQL 连接信息执行 SQL 语句（支持 DDL/DML：CREATE/ALTER/DROP/INSERT/UPDATE/DELETE/TRUNCATE 等写操作），必须经用户确认后才执行。适用于创建数据库、建表、插入数据等操作。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "MySQL 数据库资产 ID"},
            "sql": {"type": "string", "description": "要执行的 SQL 语句（支持 CREATE/ALTER/DROP/INSERT/UPDATE/DELETE 等写操作）"},
        },
        "required": ["asset_id", "sql"],
    },
    risk_level="high",
    display_name="执行 MySQL",
    expose_to_llm=False,
    location="cloud",
    category="mysql",
)
def execute_mysql(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    import pymysql
    import json as _json

    asset_id = kwargs.get("asset_id")
    sql = kwargs.get("sql", "").strip()

    if not asset_id:
        return {"error": "缺少必填参数: asset_id"}
    if not sql:
        return {"error": "缺少必填参数: sql"}

    close_db = False
    if db is None:
        db = _get_db()
        close_db = True

    try:
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            return {"error": f"资产 {asset_id} 不存在"}

        cfg = _json.loads(asset.connection_config) if asset.connection_config else {}
        host = cfg.get("db_host") or cfg.get("mysql_host") or asset.ip
        port = int(cfg.get("db_port") or cfg.get("mysql_port") or 3306)
        user = cfg.get("db_user") or cfg.get("mysql_user") or "root"
        password = cfg.get("db_password") or cfg.get("mysql_password") or ""
        database = cfg.get("db_name") or cfg.get("mysql_database") or ""

        try:
            conn = pymysql.connect(
                host=host, port=port, user=user, password=password,
                database=database, charset="utf8mb4",
                connect_timeout=10, read_timeout=60
            )
        except pymysql.Error as e:
            return {"error": f"MySQL 连接失败: {e}", "host": host, "port": port, "user": user}

        try:
            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
            affected = cur.rowcount
            return {
                "status": "success",
                "message": f"SQL 执行成功，影响行数: {affected}",
                "affected_rows": affected,
                "sql": sql,
                "asset": {"id": asset.id, "name": asset.name, "ip": asset.ip},
            }
        except pymysql.Error as e:
            conn.rollback()
            return {"error": f"SQL 执行失败: {e}", "sql": sql}
        finally:
            conn.close()
    finally:
        if close_db:
            db.close()
