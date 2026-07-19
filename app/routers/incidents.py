from fastapi import APIRouter, Depends, Request, Body
from fastapi.responses import JSONResponse
from app.template_utils import get_templates

from app.database import get_db
from app.services import incident_service, rca_service, knowledge_graph_service, config_service
from app.services.agent_service import call_llm
from app.models import AIProvider, AgentConfig
from sqlalchemy.orm import Session

router = APIRouter(prefix="/incidents", tags=["incidents"])
templates = get_templates()


def _incident_to_dict(inc, asset_name: str = "", approver_name: str = "") -> dict:
    return {
        "id": inc.id,
        "title": inc.title or "",
        "severity": inc.severity or "warning",
        "status": inc.status or "open",
        "asset_id": inc.asset_id,
        "asset_name": asset_name,
        "alert_count": inc.alert_count or 0,
        "impact": getattr(inc, "impact", "") or "",
        "description": getattr(inc, "description", "") or "",
        "approver_name": approver_name,
        "review_comment": inc.review_comment or "",
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
def api_incident_list(status: str = "", page: int = 1, per_page: int = 20, db: Session = Depends(get_db)):
    """故障单列表 JSON API."""
    incidents, total = incident_service.list_incidents(db, status, page, per_page)
    from app.models import Asset, User
    asset_ids = {inc.asset_id for inc in incidents if inc.asset_id}
    asset_map = {a.id: a.name for a in db.query(Asset).filter(Asset.id.in_(asset_ids)).all()} if asset_ids else {}
    user_ids = {inc.approver_id for inc in incidents if inc.approver_id}
    user_map = {u.id: u.username for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    return JSONResponse({
        "incidents": [_incident_to_dict(inc, asset_map.get(inc.asset_id, ""), user_map.get(inc.approver_id, "")) for inc in incidents],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    })


@router.post("/api/create")
def api_create_incident(title: str = "", severity: str = "warning", impact: str = "",
                        description: str = "", asset_id: int = None, db: Session = Depends(get_db)):
    """创建故障单 JSON API."""
    inc = incident_service.create_incident(db, title=title, severity=severity,
                                          impact=impact, description=description, asset_id=asset_id)
    if not inc:
        return JSONResponse({"message": "创建失败"}, status_code=200)
    return JSONResponse({"incident": _incident_to_dict(inc), "ok": True})


# ── 审批设置（必须在 /api/{incident_id} 之前声明，避免路径参数拦截）──
@router.get("/api/approval-settings")
def api_get_approval_settings(db: Session = Depends(get_db)):
    """获取故障单审批设置：是否启用角色校验 + 审批人 user_id 列表 + 审批人详情"""
    enabled = config_service.get_config(db, "incident_approval_enabled", "false").lower() == "true"
    approver_ids_str = config_service.get_config(db, "incident_approvers", "")
    approver_ids = [int(x) for x in approver_ids_str.split(",") if x.strip().isdigit()]

    approvers = []
    if approver_ids:
        from app.models import User
        users = db.query(User).filter(User.id.in_(approver_ids)).all()
        approvers = [{"id": u.id, "username": u.username, "role": u.role or ""} for u in users]

    return JSONResponse({
        "enabled": enabled,
        "approver_ids": approver_ids,
        "approvers": approvers,
    })


@router.put("/api/approval-settings")
def api_update_approval_settings(payload: dict = Body(...), db: Session = Depends(get_db)):
    """更新故障单审批设置

    payload:
        enabled: bool - 是否启用角色校验
        approver_ids: list[int] - 审批人 user_id 列表
    """
    enabled = bool(payload.get("enabled", False))
    approver_ids = payload.get("approver_ids", [])
    if not isinstance(approver_ids, list):
        return JSONResponse({"ok": False, "error": "approver_ids 必须是数组"}, status_code=400)

    # 校验 user_id 都存在
    if approver_ids:
        from app.models import User
        valid_ids = {u.id for u in db.query(User).filter(User.id.in_(approver_ids)).all()}
        approver_ids = [i for i in approver_ids if i in valid_ids]

    config_service.update_config(db, "incident_approval_enabled", "true" if enabled else "false")
    config_service.update_config(db, "incident_approvers", ",".join(str(i) for i in approver_ids))
    return JSONResponse({"ok": True, "enabled": enabled, "approver_ids": approver_ids})


def _check_approval_permission(db: Session, user_id: int) -> tuple[bool, str]:
    """校验当前用户是否有审批权限。

    返回 (has_permission, error_message)。
    - 若 incident_approval_enabled=false：任何人都有权限（向后兼容）
    - 若 incident_approval_enabled=true：仅当 user_id 在 incident_approvers 列表中才有权限
    """
    enabled = config_service.get_config(db, "incident_approval_enabled", "false").lower() == "true"
    if not enabled:
        return True, ""
    approver_ids_str = config_service.get_config(db, "incident_approvers", "")
    approver_ids = {int(x) for x in approver_ids_str.split(",") if x.strip().isdigit()}
    if user_id in approver_ids:
        return True, ""
    return False, "权限不足：当前用户不在审批人列表中（审批角色校验已启用）"


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


@router.post("/api/{incident_id}/submit-approval")
def api_submit_approval(incident_id: int, request: Request, comment: str = "", db: Session = Depends(get_db)):
    """提交故障单审批：open → pending_approval"""
    user_id = request.session.get("user_id")
    result = incident_service.submit_for_approval(db, incident_id, submitter_id=user_id, comment=comment)
    if not result.get("ok"):
        return JSONResponse(result, status_code=400)
    return JSONResponse(result)


@router.post("/api/{incident_id}/approve")
def api_approve_incident(incident_id: int, request: Request, comment: str = "", db: Session = Depends(get_db)):
    """审批通过：pending_approval → resolved

    权限：若 incident_approval_enabled=true，仅审批人列表中的用户可审批
    """
    user_id = request.session.get("user_id")
    has_perm, err_msg = _check_approval_permission(db, user_id)
    if not has_perm:
        return JSONResponse({"ok": False, "error": err_msg}, status_code=403)
    result = incident_service.approve_incident(db, incident_id, approver_id=user_id, comment=comment)
    if not result.get("ok"):
        return JSONResponse(result, status_code=400)
    return JSONResponse(result)


@router.post("/api/{incident_id}/reject")
def api_reject_incident(incident_id: int, request: Request, comment: str = "", db: Session = Depends(get_db)):
    """审批驳回：pending_approval → open

    权限：若 incident_approval_enabled=true，仅审批人列表中的用户可驳回
    """
    user_id = request.session.get("user_id")
    has_perm, err_msg = _check_approval_permission(db, user_id)
    if not has_perm:
        return JSONResponse({"ok": False, "error": err_msg}, status_code=403)
    result = incident_service.reject_incident(db, incident_id, approver_id=user_id, comment=comment)
    if not result.get("ok"):
        return JSONResponse(result, status_code=400)
    return JSONResponse(result)


@router.get("/api/{incident_id}/approvals")
def api_approval_history(incident_id: int, db: Session = Depends(get_db)):
    """查询故障单审批历史"""
    history = incident_service.get_approval_history(db, incident_id)
    return JSONResponse({"approvals": history})


@router.get("/api/{incident_id}/rca")
def api_incident_rca(incident_id: int, db: Session = Depends(get_db)):
    """故障单根因分析 JSON API."""
    detail = incident_service.get_incident_detail(db, incident_id)
    if not detail:
        return JSONResponse({"error": "not found"}, status_code=404)
    analysis = rca_service.analyze_incident(db, incident_id)

    # RCA 结果自动沉淀到知识库
    try:
        inc_obj = detail.get("incident")
        inc_severity = (inc_obj.severity or "warning") if inc_obj else "warning"
        knowledge_graph_service.record_rca_result(db, incident_id, analysis, severity=inc_severity)
    except Exception:
        pass

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

