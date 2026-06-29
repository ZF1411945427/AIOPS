from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ChangeRequest, ChangeTask, User
from app.template_utils import get_templates

router = APIRouter(prefix="/change-workflow", tags=["change_workflow"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def change_list(request: Request, db: Session = Depends(get_db)):
    changes = db.query(ChangeRequest).order_by(ChangeRequest.created_at.desc()).all()
    users = {u.id: u for u in db.query(User).all()}
    return templates.TemplateResponse("change_workflow.html", {
        "request": request, "changes": changes, "users": users,
    })


@router.get("/new", response_class=HTMLResponse)
def change_new_form(request: Request):
    return templates.TemplateResponse("change_workflow_form.html", {
        "request": request, "change": None,
    })


@router.post("/new")
def change_new(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    ci_type: str = Form(""),
    asset_id: int = Form(0),
    change_type: str = Form("normal"),
    priority: str = Form("medium"),
    risk_level: str = Form("low"),
    planned_start: str = Form(""),
    planned_end: str = Form(""),
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")
    c = ChangeRequest(
        title=title, description=description, ci_type=ci_type,
        asset_id=asset_id if asset_id else None,
        change_type=change_type, priority=priority, risk_level=risk_level,
        requester_id=user_id,
        planned_start=datetime.fromisoformat(planned_start) if planned_start else None,
        planned_end=datetime.fromisoformat(planned_end) if planned_end else None,
    )
    db.add(c)
    db.commit()
    return RedirectResponse(f"/change-workflow/{c.id}", status_code=303)


@router.get("/{change_id}", response_class=HTMLResponse)
def change_detail(change_id: int, request: Request, db: Session = Depends(get_db)):
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if not c:
        return RedirectResponse("/change-workflow", status_code=303)
    tasks = db.query(ChangeTask).filter(ChangeTask.change_id == change_id).order_by(ChangeTask.step_order).all()
    users = {u.id: u for u in db.query(User).all()}
    return templates.TemplateResponse("change_workflow_detail.html", {
        "request": request, "change": c, "tasks": tasks, "users": users,
    })


@router.post("/{change_id}/submit")
def change_submit(change_id: int, request: Request, db: Session = Depends(get_db)):
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if c and c.status == "draft":
        c.status = "pending_approval"
        db.commit()
    return RedirectResponse(f"/change-workflow/{change_id}", status_code=303)


@router.post("/{change_id}/approve")
def change_approve(
    change_id: int,
    request: Request,
    review_comment: str = Form(""),
    db: Session = Depends(get_db),
):
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if c and c.status == "pending_approval":
        c.status = "approved"
        c.reviewer_id = request.session.get("user_id")
        c.review_comment = review_comment
        db.commit()
    return RedirectResponse(f"/change-workflow/{change_id}", status_code=303)


@router.post("/{change_id}/reject")
def change_reject(
    change_id: int,
    request: Request,
    review_comment: str = Form(""),
    db: Session = Depends(get_db),
):
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if c and c.status == "pending_approval":
        c.status = "rejected"
        c.reviewer_id = request.session.get("user_id")
        c.review_comment = review_comment
        db.commit()
    return RedirectResponse(f"/change-workflow/{change_id}", status_code=303)


@router.post("/{change_id}/start")
def change_start(change_id: int, request: Request, db: Session = Depends(get_db)):
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if c and c.status in ("approved", "in_progress"):
        c.status = "in_progress"
        db.commit()
    return RedirectResponse(f"/change-workflow/{change_id}", status_code=303)


@router.post("/{change_id}/complete")
def change_complete(change_id: int, request: Request, db: Session = Depends(get_db)):
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if c and c.status == "in_progress":
        c.status = "completed"
        db.commit()
    return RedirectResponse(f"/change-workflow/{change_id}", status_code=303)


@router.post("/{change_id}/rollback")
def change_rollback(change_id: int, request: Request, db: Session = Depends(get_db)):
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if c and c.status in ("approved", "in_progress"):
        c.status = "rolled_back"
        db.commit()
    return RedirectResponse(f"/change-workflow/{change_id}", status_code=303)


@router.post("/{change_id}/tasks/new")
def task_new(
    change_id: int,
    request: Request,
    description: str = Form(...),
    command: str = Form(""),
    step_order: int = Form(0),
    db: Session = Depends(get_db),
):
    t = ChangeTask(change_id=change_id, description=description, command=command, step_order=step_order)
    db.add(t)
    db.commit()
    return RedirectResponse(f"/change-workflow/{change_id}", status_code=303)


@router.post("/{change_id}/tasks/{task_id}/status")
def task_update_status(
    change_id: int, task_id: int,
    request: Request,
    status: str = Form(...),
    result: str = Form(""),
    db: Session = Depends(get_db),
):
    t = db.query(ChangeTask).filter(ChangeTask.id == task_id, ChangeTask.change_id == change_id).first()
    if t:
        t.status = status
        t.result = result
        t.executed_by = request.session.get("user_id")
        if status in ("completed", "failed"):
            t.executed_at = datetime.now()
        db.commit()
    return RedirectResponse(f"/change-workflow/{change_id}", status_code=303)
