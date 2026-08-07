from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import JSONResponse
from app.template_utils import get_templates

from app.database import get_db
from app.services import remediation_service
from app.services.alert_service import list_rules
from sqlalchemy.orm import Session

router = APIRouter(prefix="/remediation", tags=["remediation"])
templates = get_templates()


def _remediation_to_dict(r) -> dict:
    import json as _json
    params = {}
    try:
        params = _json.loads(r.remediation_params) if r.remediation_params else {}
    except Exception:
        params = {}
    return {
        "id": r.id,
        "name": r.name or "",
        "rule_id": r.rule_id,
        "action_type": r.action_type or "",
        "params": params,
        "enabled": bool(r.enabled),
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
    }


def _log_to_dict(lg) -> dict:
    return {
        "id": lg.id,
        "remediation_id": lg.remediation_id,
        "alert_id": lg.alert_id,
        "action_type": lg.action_type or "",
        "target": lg.target or "",
        "is_success": bool(lg.is_success),
        "output": lg.output or "",
        "created_at": lg.created_at.strftime("%Y-%m-%d %H:%M:%S") if lg.created_at else None,
    }


@router.get("/api/list")
def api_remediation_list(db: Session = Depends(get_db)):
    """自愈规则列表 JSON API."""
    remediations = remediation_service.list_remediations(db)
    rules = list_rules(db)
    actions = {k: v["label"] for k, v in remediation_service.ACTIONS.items()}
    for alias, target in remediation_service._ACTION_ALIASES.items():
        if alias not in actions and target in actions:
            actions[alias] = actions[target]
    return JSONResponse({
        "remediations": [_remediation_to_dict(r) for r in remediations],
        "rules": [{"id": r.id, "name": r.name} for r in rules],
        "actions": actions,
        "total": len(remediations),
    })


@router.get("/api/logs")
def api_remediation_logs(page: int = 1, per_page: int = 20, db: Session = Depends(get_db)):
    """自愈执行记录分页查询 JSON API."""
    items, total, total_pages = remediation_service.get_remediation_logs_paged(db, page, per_page)
    return JSONResponse({
        "items": [_log_to_dict(lg) for lg in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    })


@router.post("/api/create")
def api_remediation_create(
    name: str = Form(...),
    rule_id: int = Form(0),
    action_type: str = Form(...),
    params_target: str = Form(""),
    params_count: int = Form(2),
    params_script: str = Form(""),
    params_command: str = Form(""),
    db: Session = Depends(get_db)):
    """创建自愈规则 JSON API."""
    import json as _json
    params = {"target": params_target}
    if action_type == "restart":
        params["service"] = params_target
    elif action_type == "clean":
        params["path"] = params_target
    elif action_type == "script":
        params["script"] = params_script or params_target
    elif action_type == "run_command":
        params["command"] = params_command or params_target
    if action_type == "scale":
        params["count"] = params_count
    r = remediation_service.create_remediation(db, {
        "name": name,
        "rule_id": rule_id if rule_id > 0 else None,
        "action_type": action_type,
        "params": params,
        "enabled": True,
    })
    return JSONResponse({"ok": True, "id": r.id})


@router.post("/api/{remediation_id}/delete")
def api_remediation_delete(remediation_id: int, db: Session = Depends(get_db)):
    """删除自愈规则 JSON API."""
    remediation_service.delete_remediation(db, remediation_id)
    return JSONResponse({"ok": True})


def _effect_to_dict(e) -> dict:
    return {
        "id": e.id,
        "remediation_id": e.remediation_id,
        "alert_id": e.alert_id,
        "executed_at": e.executed_at.strftime("%Y-%m-%d %H:%M:%S") if e.executed_at else None,
        "check_at": e.check_at.strftime("%Y-%m-%d %H:%M:%S") if e.check_at else None,
        "alert_status_at_execute": e.alert_status_at_execute or "",
        "alert_status_at_check": e.alert_status_at_check or "",
        "is_asset_recovered": bool(e.is_asset_recovered),
        "is_alert_resolved": bool(e.is_alert_resolved),
        "recovery_time_seconds": e.recovery_time_seconds or 0,
        "notes": e.description or "",
        "created_at": e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else None,
    }


@router.get("/api/effect-stats")
def api_effect_stats(days: int = 30, db: Session = Depends(get_db)):
    """自愈成功率统计 JSON API."""
    from app.services import remediation_effect_service
    stats = remediation_effect_service.get_effect_stats(db, days=days)
    return JSONResponse(stats)


@router.get("/api/effect-history")
def api_effect_history(page: int = 1, per_page: int = 20, db: Session = Depends(get_db)):
    """自愈效果历史 JSON API."""
    from app.services import remediation_effect_service
    items, total, total_pages = remediation_effect_service.get_effect_history(db, page, per_page)
    return JSONResponse({
        "items": [_effect_to_dict(e) for e in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    })


@router.get("/api/effect-recommendations")
def api_effect_recommendations(limit: int = 5, db: Session = Depends(get_db)):
    """自愈规则效果推荐 JSON API."""
    from app.services import remediation_effect_service
    recs = remediation_effect_service.get_remediation_recommendations(db, limit=limit)
    return JSONResponse({"items": recs})


# ── AI 自愈工作台 API ──

@router.get("/api/triggered-alerts")
def api_triggered_alerts(limit: int = 30, db: Session = Depends(get_db)):
    """获取触发中的告警列表."""
    alerts = remediation_service.get_triggered_alerts(db, limit=limit)
    return JSONResponse({"alerts": alerts, "total": len(alerts)})


@router.post("/api/ai-analyze/{alert_id}")
def api_ai_analyze(alert_id: int, request: Request, db: Session = Depends(get_db)):
    """AI 自愈分析告警：分析根因 + 生成修复建议 + 创建待审批动作."""
    username = request.session.get("username", "admin")
    result = remediation_service.ai_self_heal_analyze(db, alert_id)
    return JSONResponse(result)


@router.get("/api/ai-pending")
def api_ai_pending(status: str = "all", limit: int = 50, db: Session = Depends(get_db)):
    """获取 AI 自愈的待审批动作."""
    items = remediation_service.get_ai_pending_actions(db, status=status, limit=limit)
    return JSONResponse({"items": items, "total": len(items)})


@router.post("/api/ai-pending/{action_id}/confirm")
def api_ai_confirm(action_id: int, request: Request, db: Session = Depends(get_db)):
    """确认 AI 自愈动作并执行."""
    username = request.session.get("username", "admin")
    result = remediation_service.confirm_ai_action(db, action_id, username=username)
    return JSONResponse(result)


@router.post("/api/ai-pending/{action_id}/cancel")
def api_ai_cancel(action_id: int, db: Session = Depends(get_db)):
    """取消 AI 自愈动作."""
    result = remediation_service.cancel_ai_action(db, action_id)
    return JSONResponse(result)


# ── 诊断报告 API ──

@router.post("/api/diagnose/{alert_id}")
def api_diagnose_alert(alert_id: int, force: bool = False, db: Session = Depends(get_db)):
    """对指定告警执行自动诊断（手动触发 / 重新诊断）."""
    result = remediation_service.run_diagnosis(db, alert_id, force=force)
    return JSONResponse(result)


@router.get("/api/diagnosis/{report_id}")
def api_diagnosis_report(report_id: int, db: Session = Depends(get_db)):
    """获取诊断报告详情."""
    result = remediation_service.get_diagnosis_report(db, report_id)
    return JSONResponse(result)


@router.post("/api/ai-reanalyze/{action_id}")
def api_ai_reanalyze(action_id: int, db: Session = Depends(get_db)):
    """基于失败经验重新分析，生成新修复方案."""
    result = remediation_service.reanalyze_with_failure_context(db, action_id)
    return JSONResponse(result)


@router.post("/api/ai-reanalyze-alert/{alert_id}")
def api_ai_reanalyze_alert(alert_id: int, db: Session = Depends(get_db)):
    """对指定告警重新 AI 分析（取消旧 PA，生成新方案，让 AI 考虑工作流并填参数）."""
    result = remediation_service.reanalyze_alert(db, alert_id)
    return JSONResponse(result)


