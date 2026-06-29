from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.template_utils import get_templates

from app.database import get_db
from app.services import remediation_service
from app.services.alert_service import list_rules
from sqlalchemy.orm import Session

router = APIRouter(prefix="/remediation", tags=["remediation"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def remediation_page(request: Request, db: Session = Depends(get_db)):
    remediations = remediation_service.list_remediations(db)
    rules = list_rules(db)
    logs = remediation_service.get_remediation_logs(db)
    return templates.TemplateResponse("remediation.html", {
        "request": request,
        "remediations": remediations,
        "rules": rules,
        "logs": logs,
        "actions": remediation_service.ACTIONS,
    })


@router.post("/create")
def remediation_create(
    name: str = Form(...),
    rule_id: int = Form(0),
    action_type: str = Form(...),
    params_target: str = Form(""),
    params_count: int = Form(2),
    params_script: str = Form(""),
    db: Session = Depends(get_db),
):
    params = {"target": params_target}
    if action_type == "scale":
        params["count"] = params_count
    if action_type == "script":
        params["script"] = params_script
    remediation_service.create_remediation(db, {
        "name": name,
        "rule_id": rule_id if rule_id > 0 else None,
        "action_type": action_type,
        "params": params,
        "enabled": True,
    })
    return RedirectResponse("/remediation", status_code=303)


@router.post("/{remediation_id}/delete")
def remediation_delete(remediation_id: int, db: Session = Depends(get_db)):
    remediation_service.delete_remediation(db, remediation_id)
    return RedirectResponse("/remediation", status_code=303)


