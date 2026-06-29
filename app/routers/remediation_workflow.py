import json
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import RemediationWorkflow, RemediationLog, Alert
from app.services.remediation_service import get_remediation_logs
from app.template_utils import get_templates

router = APIRouter(prefix="/remediation-workflows", tags=["remediation_workflows"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def list_workflows(request: Request, db: Session = Depends(get_db)):
    workflows = db.query(RemediationWorkflow).order_by(RemediationWorkflow.id.desc()).all()
    for w in workflows:
        w.steps_list = json.loads(w.steps) if isinstance(w.steps, str) else w.steps or []
    logs = get_remediation_logs(db)
    return templates.TemplateResponse("remediation_workflows.html", {
        "request": request, "workflows": workflows, "logs": logs,
    })


@router.get("/new", response_class=HTMLResponse)
def new_workflow(request: Request):
    return templates.TemplateResponse("remediation_workflow_form.html", {
        "request": request, "wf": None,
    })


@router.post("/new")
def create_workflow(
    request: Request,
    name: str = Form(...),
    steps: str = Form("[]"),
    rule_id: int = Form(0),
    db: Session = Depends(get_db),
):
    try:
        steps_list = json.loads(steps)
    except Exception:
        steps_list = [s.strip() for s in steps.split("\n") if s.strip()]
    wf = RemediationWorkflow(
        name=name,
        rule_id=rule_id if rule_id else None,
        steps=json.dumps(steps_list, ensure_ascii=False),
        enabled=True,
    )
    db.add(wf)
    db.commit()
    return RedirectResponse("/remediation-workflows", status_code=303)


@router.post("/{wf_id}/toggle")
def toggle_workflow(wf_id: int, db: Session = Depends(get_db)):
    wf = db.query(RemediationWorkflow).filter(RemediationWorkflow.id == wf_id).first()
    if wf:
        wf.enabled = not wf.enabled
        db.commit()
    return RedirectResponse("/remediation-workflows", status_code=303)


@router.post("/{wf_id}/delete")
def delete_workflow(wf_id: int, db: Session = Depends(get_db)):
    wf = db.query(RemediationWorkflow).filter(RemediationWorkflow.id == wf_id).first()
    if wf:
        db.delete(wf)
        db.commit()
    return RedirectResponse("/remediation-workflows", status_code=303)


@router.post("/{wf_id}/run")
def run_workflow(wf_id: int, db: Session = Depends(get_db)):
    wf = db.query(RemediationWorkflow).filter(RemediationWorkflow.id == wf_id).first()
    if not wf:
        return RedirectResponse("/remediation-workflows", status_code=303)
    steps = json.loads(wf.steps) if isinstance(wf.steps, str) else wf.steps or []
    alerts = db.query(Alert).filter(Alert.status == "triggered").order_by(Alert.created_at.desc()).limit(3).all()
    for alert in alerts:
        for step_idx, step in enumerate(steps):
            action_type = step.get("action", "restart") if isinstance(step, dict) else step
            target = f"asset_{alert.asset_id}"
            success, output = _run_step(action_type, target)
            log = RemediationLog(
                remediation_id=wf.id,
                alert_id=alert.id,
                action_type=action_type,
                target=target,
                success=success,
                output=f"[Step {step_idx+1}/{len(steps)}] {output}",
            )
            db.add(log)
            if not success:
                break
        alert.status = "acknowledged"
    db.commit()
    return RedirectResponse("/remediation-workflows", status_code=303)


def _run_step(action_type: str, target: str):
    """执行修复步骤 — 调用真实修复服务，不使用 random 模拟"""
    from app.services.remediation_service import execute_action
    return execute_action(action_type, {}, target)
