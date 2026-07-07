import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from app.template_utils import get_templates

from datetime import datetime

from app.database import get_db
from app.services import alert_service
from app.models import Alert, AlertSilence, RemediationWorkflow, RemediationLog, Asset
from app.services.remediation_service import execute_action
from sqlalchemy.orm import Session

router = APIRouter(prefix="/alerts", tags=["alerts"])
templates = get_templates()


@router.post("/check")
def check_alerts(db: Session = Depends(get_db)):
    new_alerts = alert_service.check_rules(db)
    return {"new_alerts": len(new_alerts)}


def _alert_to_dict(a):
    return {
        "id": a.id,
        "metric_name": a.metric_name,
        "actual_value": a.actual_value,
        "threshold": a.threshold,
        "severity": a.severity,
        "status": a.status,
        "message": a.message,
        "asset_id": getattr(a, "asset_id", None),
        "rule_id": getattr(a, "rule_id", None),
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else None,
        "acknowledged_at": a.acknowledged_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(a, "acknowledged_at", None) else None,
        "resolved_at": a.resolved_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(a, "resolved_at", None) else None,
    }


@router.get("/api/list")
def api_alert_list(
    status: str = "",
    severity: str = "",
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db)):
    """告警列表 JSON API."""
    alerts, total = alert_service.list_alerts(db, status, severity, page, per_page)
    stats = alert_service.get_alert_stats(db)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    return JSONResponse({
        "alerts": [_alert_to_dict(a) for a in alerts],
        "stats": stats,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    })


@router.post("/api/batch-acknowledge")
def api_batch_acknowledge(db: Session = Depends(get_db)):
    count = alert_service.batch_acknowledge(db)
    return JSONResponse({"acknowledged": count})


@router.post("/api/batch-resolve")
def api_batch_resolve(db: Session = Depends(get_db)):
    count = alert_service.batch_resolve(db)
    return JSONResponse({"resolved": count})


@router.post("/api/check")
def api_check_alerts(db: Session = Depends(get_db)):
    new_alerts = alert_service.check_rules(db)
    return JSONResponse({"new_alerts": len(new_alerts)})


@router.post("/api/{alert_id}/acknowledge")
def api_acknowledge_alert(alert_id: int, db: Session = Depends(get_db)):
    alert_service.acknowledge_alert(db, alert_id)
    return JSONResponse({"ok": True})


@router.post("/api/{alert_id}/resolve")
def api_resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    alert_service.resolve_alert(db, alert_id)
    return JSONResponse({"ok": True})


@router.post("/api/{alert_id}/heal")
def api_heal_alert(alert_id: int, db: Session = Depends(get_db)):
    """触发自愈：对指定告警运行第一个启用的自愈工作流."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return JSONResponse({"error": "告警不存在"}, status_code=404)

    wf = db.query(RemediationWorkflow).filter(
        RemediationWorkflow.enabled == True
    ).order_by(RemediationWorkflow.id.asc()).first()
    if not wf:
        return JSONResponse({"error": "没有启用的自愈工作流"}, status_code=400)

    steps = json.loads(wf.steps) if isinstance(wf.steps, str) else (wf.steps or [])
    asset = db.query(Asset).filter(Asset.id == alert.asset_id).first() if alert.asset_id else None
    target = asset.name if asset else f"asset_{alert.asset_id}"
    results = []

    for step_idx, step in enumerate(steps):
        if isinstance(step, dict):
            action_type = step.get("action", "restart")
            params = {k: v for k, v in step.items() if k not in ("step", "action")}
        else:
            action_type = step
            params = {}
        if not asset:
            success, output = False, f"未找到资产 alert.asset_id={alert.asset_id}，无法远程执行"
        else:
            success, output = execute_action(action_type, params, asset)
        log = RemediationLog(
            remediation_id=wf.id,
            alert_id=alert.id,
            action_type=action_type,
            target=target,
            success=success,
            output=f"[Step {step_idx+1}/{len(steps)}] {output}")
        db.add(log)
        results.append({"step": step_idx + 1, "action": action_type, "success": success, "output": output})
        if not success:
            break

    alert.status = "acknowledged"
    db.commit()

    return JSONResponse({"ok": True, "alert_id": alert.id, "workflow": wf.name, "steps": results})


