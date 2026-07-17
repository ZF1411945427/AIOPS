import json
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import RemediationWorkflow, RemediationLog, Alert, Asset
from app.services.remediation_service import get_remediation_logs
from app.template_utils import get_templates

router = APIRouter(prefix="/remediation-workflows", tags=["remediation_workflows"])
templates = get_templates()


def _run_step(action_type: str, params: dict, asset: Asset):
    """执行修复步骤 — 调用真实修复服务，不使用 random 模拟"""
    from app.services.remediation_service import execute_action
    return execute_action(action_type, params, asset)


# ─── JSON API（供 Vue 前端调用，保留 HTML 路由作 fallback）───

def _workflow_to_dict(w) -> dict:
    steps = json.loads(w.steps) if isinstance(w.steps, str) else (w.steps or [])
    return {
        "id": w.id,
        "name": w.name or "",
        "rule_id": w.rule_id,
        "steps": steps if isinstance(steps, list) else [],
        "enabled": bool(w.enabled),
        "created_at": w.created_at.strftime("%Y-%m-%d %H:%M:%S") if w.created_at else None,
    }


def _wf_log_to_dict(lg) -> dict:
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
def api_workflow_list(db: Session = Depends(get_db)):
    """自愈工作流列表 JSON API."""
    workflows = db.query(RemediationWorkflow).order_by(RemediationWorkflow.id.desc()).all()
    return JSONResponse({
        "workflows": [_workflow_to_dict(w) for w in workflows],
        "total": len(workflows),
    })


@router.get("/api/logs")
def api_workflow_logs(page: int = 1, per_page: int = 20, db: Session = Depends(get_db)):
    """自愈日志分页查询 JSON API."""
    from app.services.remediation_service import get_remediation_logs_paged
    items, total, total_pages = get_remediation_logs_paged(db, page, per_page)
    return JSONResponse({
        "items": [_wf_log_to_dict(lg) for lg in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    })


@router.post("/api/create")
def api_workflow_create(
    name: str = Form(...),
    steps: str = Form("[]"),
    rule_id: int = Form(0),
    db: Session = Depends(get_db)):
    """创建自愈工作流 JSON API."""
    try:
        steps_list = json.loads(steps)
    except Exception:
        steps_list = [s.strip() for s in steps.split("\n") if s.strip()]
    wf = RemediationWorkflow(
        name=name,
        rule_id=rule_id if rule_id else None,
        steps=json.dumps(steps_list, ensure_ascii=False),
        enabled=True)
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return JSONResponse({"ok": True, "id": wf.id})


@router.post("/api/{wf_id}/toggle")
def api_workflow_toggle(wf_id: int, db: Session = Depends(get_db)):
    """启用/禁用自愈工作流 JSON API."""
    wf = db.query(RemediationWorkflow).filter(RemediationWorkflow.id == wf_id).first()
    if not wf:
        return JSONResponse({"error": "not found"}, status_code=404)
    wf.enabled = not wf.enabled
    db.commit()
    return JSONResponse({"ok": True, "enabled": bool(wf.enabled)})


@router.post("/api/{wf_id}/delete")
def api_workflow_delete(wf_id: int, db: Session = Depends(get_db)):
    """删除自愈工作流 JSON API."""
    wf = db.query(RemediationWorkflow).filter(RemediationWorkflow.id == wf_id).first()
    if not wf:
        return JSONResponse({"error": "not found"}, status_code=404)
    db.delete(wf)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/api/{wf_id}/run")
def api_workflow_run(wf_id: int, db: Session = Depends(get_db)):
    """运行自愈工作流 JSON API."""
    wf = db.query(RemediationWorkflow).filter(RemediationWorkflow.id == wf_id).first()
    if not wf:
        return JSONResponse({"error": "not found"}, status_code=404)
    steps = json.loads(wf.steps) if isinstance(wf.steps, str) else (wf.steps or [])
    alerts = db.query(Alert).filter(Alert.status == "triggered").order_by(Alert.created_at.desc()).limit(3).all()
    ran = 0
    for alert in alerts:
        asset = db.query(Asset).filter(Asset.id == alert.asset_id).first() if alert.asset_id else None
        for step_idx, step in enumerate(steps):
            if isinstance(step, dict):
                action_type = step.get("action", "restart")
                params = {k: v for k, v in step.items() if k not in ("step", "action")}
            else:
                action_type = step
                params = {}
            target = asset.name if asset else f"asset_{alert.asset_id}"
            if not asset:
                success, output = False, f"未找到资产 alert.asset_id={alert.asset_id}，无法远程执行"
            else:
                success, output = _run_step(action_type, params, asset)
            log = RemediationLog(
                remediation_id=wf.id,
                alert_id=alert.id,
                action_type=action_type,
                target=target,
                is_success=success,
                output=f"[Step {step_idx+1}/{len(steps)}] {output}")
            db.add(log)
            if not success:
                break
        alert.status = "acknowledged"
        ran += 1
    db.commit()
    return JSONResponse({"ok": True, "ran": ran})
