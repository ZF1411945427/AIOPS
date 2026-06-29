import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import Alert, AlertRule, Asset, ChatSession, MetricRecord, K8sEvent, Incident, KnowledgeBase
from app.services.mcp_registry import register_mcp_tool


def _get_db():
    return get_session_for(get_db_mode())()


# ─── Alert Tools ───────────────────────────────────────────────

@register_mcp_tool(
    name="query_alerts",
    description="查询告警列表，支持按状态、级别、时间范围筛选",
    input_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "告警状态: triggered, acknowledged, resolved"},
            "severity": {"type": "string", "description": "严重级别: warning, critical"},
            "limit": {"type": "integer", "description": "返回数量限制", "default": 10},
        },
    },
    risk_level="read_only",
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
        limit = kwargs.get("limit", 10)
        alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()
        return {
            "count": len(alerts),
            "alerts": [
                {
                    "id": a.id,
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
    description="查询资产列表，支持按类型、状态、名称搜索",
    input_schema={
        "type": "object",
        "properties": {
            "ci_type": {"type": "string", "description": "资产类型: server, pod, deployment, service, node, cluster 等"},
            "status": {"type": "string", "description": "状态: online, offline, warning"},
            "search": {"type": "string", "description": "名称搜索关键字"},
            "limit": {"type": "integer", "description": "返回数量限制", "default": 20},
        },
    },
    risk_level="read_only",
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
            query = query.filter(Asset.name.ilike(f"%{kwargs['search']}%"))
        limit = kwargs.get("limit", 20)
        assets = query.order_by(Asset.name).limit(limit).all()
        return {
            "count": len(assets),
            "assets": [
                {
                    "id": a.id,
                    "name": a.name,
                    "type": a.type,
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
    description="查询指标最新值或历史趋势",
    input_schema={
        "type": "object",
        "properties": {
            "metric_name": {"type": "string", "description": "指标名称，如 cpu_usage, memory_usage, disk_usage"},
            "asset_id": {"type": "integer", "description": "资产 ID（可选）"},
            "hours": {"type": "integer", "description": "查询最近多少小时的数据", "default": 1},
            "limit": {"type": "integer", "description": "返回数据点数量", "default": 60},
        },
    },
    risk_level="read_only",
)
def query_metrics(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        metric_name = kwargs.get("metric_name", "")
        asset_id = kwargs.get("asset_id")
        hours = kwargs.get("hours", 1)
        limit = kwargs.get("limit", 60)

        query = db.query(MetricRecord).filter(MetricRecord.metric_name == metric_name)
        if asset_id:
            query = query.filter(MetricRecord.asset_id == asset_id)
        cutoff = datetime.now() - timedelta(hours=hours)
        query = query.filter(MetricRecord.created_at >= cutoff)
        records = query.order_by(MetricRecord.created_at.desc()).limit(limit).all()

        values = [{"value": r.value, "time": str(r.created_at)} for r in records]
        values.reverse()

        avg_value = sum(r.value for r in records) / len(records) if records else 0
        max_value = max(r.value for r in records) if records else 0
        min_value = min(r.value for r in records) if records else 0

        return {
            "metric_name": metric_name,
            "count": len(values),
            "avg": round(avg_value, 2),
            "max": round(max_value, 2),
            "min": round(min_value, 2),
            "latest": values[-1] if values else None,
            "values": values,
        }
    finally:
        if close_db:
            db.close()


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


# ─── Knowledge Tools ───────────────────────────────────────────

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
                    "type": e.event_type,
                    "reason": e.reason,
                    "message": e.message,
                    "involved_object": e.involved_object,
                    "severity": e.severity,
                    "cluster": e.cluster,
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
        result = analyze_incident(db, incident)
        return result
    finally:
        if close_db:
            db.close()
