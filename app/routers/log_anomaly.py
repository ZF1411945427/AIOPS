from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import LogAnomalyRule
from app.template_utils import get_templates

router = APIRouter(prefix="/log-anomaly", tags=["log_anomaly"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def list_rules(request: Request, db: Session = Depends(get_db)):
    rules = db.query(LogAnomalyRule).order_by(LogAnomalyRule.id.desc()).all()
    return templates.TemplateResponse("log_anomaly_rules.html", {
        "request": request, "rules": rules,
    })


@router.get("/new", response_class=HTMLResponse)
def new_rule(request: Request):
    return templates.TemplateResponse("log_anomaly_form.html", {
        "request": request, "rule": None,
    })


@router.post("/new")
def create_rule(
    request: Request,
    name: str = Form(...),
    source: str = Form("k8s"),
    keyword: str = Form(""),
    regex_pattern: str = Form(""),
    threshold: int = Form(10),
    window_minutes: int = Form(5),
    severity: str = Form("warning"),
    db: Session = Depends(get_db),
):
    r = LogAnomalyRule(
        name=name, source=source, keyword=keyword,
        regex_pattern=regex_pattern, threshold=threshold,
        window_minutes=window_minutes, severity=severity,
        enabled=True,
    )
    db.add(r)
    db.commit()
    return RedirectResponse("/log-anomaly", status_code=303)


@router.post("/{rule_id}/toggle")
def toggle_rule(rule_id: int, db: Session = Depends(get_db)):
    r = db.query(LogAnomalyRule).filter(LogAnomalyRule.id == rule_id).first()
    if r:
        r.enabled = not r.enabled
        db.commit()
    return RedirectResponse("/log-anomaly", status_code=303)


@router.post("/{rule_id}/delete")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    r = db.query(LogAnomalyRule).filter(LogAnomalyRule.id == rule_id).first()
    if r:
        db.delete(r)
        db.commit()
    return RedirectResponse("/log-anomaly", status_code=303)
