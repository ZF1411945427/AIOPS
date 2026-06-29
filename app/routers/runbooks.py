from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Runbook
from app.template_utils import get_templates

templates = get_templates()

router = APIRouter(prefix="/runbooks", tags=["runbooks"])


@router.get("", response_class=HTMLResponse)
def list_runbooks(request: Request, category: str = "", db: Session = Depends(get_db)):
    q = db.query(Runbook)
    if category:
        q = q.filter(Runbook.category == category)
    runbooks = q.order_by(Runbook.updated_at.desc()).all()
    cats = [r[0] for r in db.query(Runbook.category).distinct().all()]
    return templates.TemplateResponse("runbooks.html", {
        "request": request, "runbooks": runbooks, "current_cat": category, "categories": cats,
    })


@router.get("/new", response_class=HTMLResponse)
def new_runbook(request: Request):
    return templates.TemplateResponse("runbook_form.html", {"request": request, "rb": None})


@router.post("/new")
def create_runbook(
    title: str = Form(...),
    category: str = Form("general"),
    symptom: str = Form(""),
    diagnosis: str = Form(""),
    steps: str = Form(""),
    tags: str = Form(""),
    severity: str = Form("warning"),
    asset_type: str = Form(""),
    db: Session = Depends(get_db),
):
    rb = Runbook(
        title=title, category=category, symptom=symptom,
        diagnosis=diagnosis, steps=steps, tags=tags,
        severity=severity, asset_type=asset_type,
    )
    db.add(rb)
    db.commit()
    return RedirectResponse("/runbooks", status_code=303)


@router.get("/{rb_id}", response_class=HTMLResponse)
def view_runbook(rb_id: int, request: Request, db: Session = Depends(get_db)):
    rb = db.query(Runbook).filter(Runbook.id == rb_id).first()
    if not rb:
        return RedirectResponse("/runbooks", status_code=303)
    return templates.TemplateResponse("runbook_detail.html", {"request": request, "rb": rb})


@router.get("/{rb_id}/edit", response_class=HTMLResponse)
def edit_runbook(rb_id: int, request: Request, db: Session = Depends(get_db)):
    rb = db.query(Runbook).filter(Runbook.id == rb_id).first()
    if not rb:
        return RedirectResponse("/runbooks", status_code=303)
    return templates.TemplateResponse("runbook_form.html", {"request": request, "rb": rb})


@router.post("/{rb_id}/edit")
def update_runbook(rb_id: int, request: Request, db: Session = Depends(get_db)):
    rb = db.query(Runbook).filter(Runbook.id == rb_id).first()
    if not rb:
        return RedirectResponse("/runbooks", status_code=303)
    form = request.form()
    rb.title = form["title"]
    rb.category = form.get("category", "general")
    rb.symptom = form.get("symptom", "")
    rb.diagnosis = form.get("diagnosis", "")
    rb.steps = form.get("steps", "")
    rb.tags = form.get("tags", "")
    rb.severity = form.get("severity", "warning")
    rb.asset_type = form.get("asset_type", "")
    db.commit()
    return RedirectResponse(f"/runbooks/{rb_id}", status_code=303)


@router.post("/{rb_id}/delete")
def delete_runbook(rb_id: int, db: Session = Depends(get_db)):
    rb = db.query(Runbook).filter(Runbook.id == rb_id).first()
    if rb:
        db.delete(rb)
        db.commit()
    return RedirectResponse("/runbooks", status_code=303)
