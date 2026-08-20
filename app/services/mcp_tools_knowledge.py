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

# ─── 代码/git 知识库工具(P2-5) ──────────────────────────────────

@register_mcp_tool(
    name="search_code",
    description="在已同步的 git 代码仓库中按关键词搜索代码(返回文件:行号:片段)。需先通过 git 知识库同步仓库",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词(子串匹配)"},
            "repo": {"type": "string", "description": "限定仓库名(可选, 不填搜全部)"},
            "limit": {"type": "integer", "description": "返回条数上限", "default": 10},
        },
        "required": ["query"],
    },
    risk_level="read_only",
    display_name="搜索代码",
    location="cloud",
    category="knowledge",
)
def search_code(db=None, user_id=None, **kwargs):
    from app.services import git_knowledge_service
    session = _get_db()
    try:
        result = git_knowledge_service.search_code(
            session, kwargs.get("query") or "", kwargs.get("repo"), int(kwargs.get("limit") or 10))
        return {"status": "success", "result": result}
    finally:
        session.close()
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
            "asset_id": {"type": "integer", "description": "资产ID过滤（可选）。当用户提到某具体资产/主机/服务时，传入该资产ID，只检索该资产关联的部署文档、运维知识，如 query_knowledge_rag(query='部署方式', asset_id=5)"},
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
    timeout_seconds=45,
    ratelimit_per_minute=60,
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
            asset_id=kwargs.get("asset_id") or None,
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
