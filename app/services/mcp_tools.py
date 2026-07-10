import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import Alert, AlertRule, Asset, ChatSession, MetricRecord, K8sEvent, Incident, KnowledgeBase
from app.services.mcp_registry import register_mcp_tool, get_internal_tools, get_mcp_tool
from app.services import remediation_service, alert_service, incident_service, asset_service, rag_service


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
    expose_to_llm=False,
)
def execute_restart_service(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        service = kwargs.get("service")
        asset_id = kwargs.get("asset_id")
        if not service:
            raise ValueError("缺少必填参数: service")
        if asset_id is None:
            raise ValueError("缺少必填参数: asset_id")
        # 查资产记录：执行目标必须是 CMDB 中已登记的资产，绝不本机执行
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            raise ValueError(f"资产 id={asset_id} 不存在")
        if asset.status != "online":
            raise ValueError(f"资产 {asset.name} 当前状态为 {asset.status}，仅 online 资产可远程执行")
        if asset.connection_type != "ssh":
            raise ValueError(f"资产 {asset.name} 连接类型为 {asset.connection_type}，仅 ssh 类型支持远程执行")
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
    expose_to_llm=False,
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
            raise ValueError(f"资产 {asset.name} 连接类型为 {asset.connection_type}，仅 ssh 类型支持远程执行")
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
    expose_to_llm=False,
)
def execute_run_script(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        script = kwargs.get("script")
        asset_id = kwargs.get("asset_id")
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
            raise ValueError(f"资产 {asset.name} 连接类型为 {asset.connection_type}，仅 ssh 类型支持远程执行")
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
    expose_to_llm=False,
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
            raise ValueError(f"资产 {asset.name} 连接类型为 {asset.connection_type}，仅 ssh 类型支持远程执行")
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
    expose_to_llm=False,
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
    expose_to_llm=False,
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
    expose_to_llm=False,
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
    expose_to_llm=False,
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
        return {"status": "success", "message": f"规则 {rule_id} 已静默 {minutes} 分钟", "data": {"silence_id": silence.id, "rule_id": silence.rule_id, "until": str(silence.until)}}
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
    expose_to_llm=False,
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
    expose_to_llm=False,
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
    expose_to_llm=False,
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
    expose_to_llm=False,
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
    expose_to_llm=False,
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
    expose_to_llm=False,
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
    expose_to_llm=False,
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
    expose_to_llm=True,
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
    expose_to_llm=True,
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
        templates = workflow_service.list_templates(db, category=category, only_enabled=only_enabled)
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
