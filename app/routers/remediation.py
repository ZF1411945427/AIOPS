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
    if action_type == "scale":
        params["count"] = params_count
    if action_type == "script":
        params["script"] = params_script
    if action_type == "run_command":
        params["command"] = params_command
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


