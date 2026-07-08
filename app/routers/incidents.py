from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from app.template_utils import get_templates

from app.database import get_db
from app.services import incident_service, rca_service
from app.services.agent_service import call_llm
from app.models import AIProvider, AgentConfig
from sqlalchemy.orm import Session

router = APIRouter(prefix="/incidents", tags=["incidents"])
templates = get_templates()


def _incident_to_dict(inc, asset_name: str = "") -> dict:
    return {
        "id": inc.id,
        "title": inc.title or "",
        "severity": inc.severity or "warning",
        "status": inc.status or "open",
        "asset_id": inc.asset_id,
        "asset_name": asset_name,
        "alert_count": inc.alert_count or 0,
        "created_at": inc.created_at.strftime("%Y-%m-%d %H:%M:%S") if inc.created_at else None,
        "resolved_at": inc.resolved_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(inc, "resolved_at", None) else None,
    }


def _alert_to_dict(a) -> dict:
    return {
        "id": a.id,
        "metric_name": a.metric_name,
        "actual_value": a.actual_value,
        "threshold": a.threshold,
        "severity": a.severity,
        "status": a.status,
        "message": a.message or "",
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else None,
    }


@router.get("/api/list")
def api_incident_list(status: str = "", db: Session = Depends(get_db)):
    """故障单列表 JSON API."""
    incidents = incident_service.list_incidents(db, status)
    from app.models import Asset
    asset_ids = {inc.asset_id for inc in incidents if inc.asset_id}
    asset_map = {a.id: a.name for a in db.query(Asset).filter(Asset.id.in_(asset_ids)).all()} if asset_ids else {}
    return JSONResponse({
        "incidents": [_incident_to_dict(inc, asset_map.get(inc.asset_id, "")) for inc in incidents],
        "total": len(incidents),
    })


@router.get("/api/{incident_id}")
def api_incident_detail(incident_id: int, db: Session = Depends(get_db)):
    """故障单详情 JSON API."""
    detail = incident_service.get_incident_detail(db, incident_id)
    if not detail:
        return JSONResponse({"error": "not found"}, status_code=404)
    inc = detail["incident"]
    asset = detail["asset"]
    return JSONResponse({
        "incident": _incident_to_dict(inc, asset.name if asset else ""),
        "alerts": [_alert_to_dict(a) for a in detail["alerts"]],
        "asset": {"id": asset.id, "name": asset.name, "ip": asset.ip or ""} if asset else None,
    })


@router.post("/api/{incident_id}/resolve")
def api_resolve_incident(incident_id: int, db: Session = Depends(get_db)):
    """解决故障单 JSON API."""
    inc = incident_service.resolve_incident(db, incident_id)
    if not inc:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"ok": True})


@router.get("/api/{incident_id}/rca")
def api_incident_rca(incident_id: int, db: Session = Depends(get_db)):
    """故障单根因分析 JSON API."""
    detail = incident_service.get_incident_detail(db, incident_id)
    if not detail:
        return JSONResponse({"error": "not found"}, status_code=404)
    analysis = rca_service.analyze_incident(db, incident_id)

    def _safe(obj):
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "__dict__"):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        return str(obj)
    return JSONResponse({"analysis": _safe(analysis)})


@router.post("/api/{incident_id}/ai-rca")
def api_incident_ai_rca(incident_id: int, db: Session = Depends(get_db)):
    """AI 深度根因分析：结合算法 RCA 结果 + 告警详情，调用 LLM 给出自然语言分析."""
    detail = incident_service.get_incident_detail(db, incident_id)
    if not detail:
        return JSONResponse({"error": "故障单不存在"}, status_code=404)
    inc = detail["incident"]
    asset = detail["asset"]
    alerts = detail["alerts"]
    analysis = rca_service.analyze_incident(db, incident_id)

    # 找可用的 AI provider
    config = db.query(AgentConfig).filter(AgentConfig.id == 1).first()
    provider = None
    if config and config.default_provider_id:
        provider = db.query(AIProvider).filter(
            AIProvider.id == config.default_provider_id,
            AIProvider.is_enabled == True,
        ).first()
    if not provider:
        provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    if not provider:
        return JSONResponse({"ok": False, "error": "未配置 AI 提供商，请在「智能体配置 > AI 提供商」中添加并启用"}, status_code=400)

    # 格式化告警明细
    alert_lines = []
    for a in alerts:
        m = a.message or ""
        alert_lines.append(f"- [{a.severity}] {a.metric_name} = {a.actual_value} (阈值: {a.threshold}) | 资产ID: {a.asset_id} | {m[:120]}")
    alert_text = "\n".join(alert_lines) if alert_lines else "无关联告警"

    # 格式化涉事资产
    asset_lines = []
    for ia in analysis.get("involved_assets", []):
        asset_lines.append(f"- {ia['name']} (类型: {ia.get('type', '?')}, 告警数: {ia['alert_count']}, RCA评分: {ia['rca_score']})")
    asset_text = "\n".join(asset_lines) if asset_lines else "无"

    # 格式化传播路径
    path_lines = []
    for p in analysis.get("propagation_paths", []):
        path_lines.append(f"- {p['from']} → {p['to']}: 路径 {p['path']}")
    path_text = "\n".join(path_lines) if path_lines else "无传播路径"

    rc = analysis.get("root_cause") or {}

    prompt = f"""你是一个资深 SRE 根因分析专家。请根据以下故障单信息进行深度分析，用中文输出。

## 故障单概况
- ID: {incident_id}
- 标题: {inc.title or '无'}
- 级别: {inc.severity or 'warning'}
- 关联资产: {asset.name if asset else '无'} (IP: {asset.ip if asset else 'N/A'})

## 算法 RCA 结论（基于拓扑依赖评分）
- 根因资产: {rc.get('name', '未知')} (评分: {rc.get('score', 0)})
- 告警总数: {analysis.get('total_alerts', 0)}
- 严重性分布: {analysis.get('severity_distribution', {})}

## 涉事资产列表（按 RCA 评分排序）
{asset_text}

## 传播路径（根因→其他资产）
{path_text}

## 关联告警明细
{alert_text}

请依次分析：
1. **可能的根因分析**：结合拓扑依赖评分最高的节点和告警内容，推断最可能的根本原因
2. **故障传播链**：描述故障如何从根因节点传播到其他节点
3. **修复建议**：给出具体的、可操作的前 3 条修复步骤（按紧急程度排序）
4. **风险提示**：需要重点关注的事项"""

    messages = [
        {"role": "system", "content": "你是资深 SRE 根因分析专家，根据告警数据和拓扑关系给出精准的根因分析和可操作的修复建议。回答简洁专业，用中文。"},
        {"role": "user", "content": prompt},
    ]
    result = call_llm(provider, messages, timeout_override=60)
    if "error" in result:
        return JSONResponse({"ok": False, "error": f"AI 调用失败: {result['error']}"}, status_code=502)
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = str(result)

    return JSONResponse({"ok": True, "analysis": content})


# ─── HTML 路由（fallback）───

