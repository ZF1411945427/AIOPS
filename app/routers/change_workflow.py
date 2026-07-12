from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ChangeRequest, ChangeTask, User
from app.template_utils import get_templates

router = APIRouter(prefix="/change-workflow", tags=["change_workflow"])
templates = get_templates()


def _change_to_dict(c, users: dict) -> dict:
    requester = users.get(c.requester_id)
    reviewer = users.get(c.reviewer_id)
    return {
        "id": c.id,
        "title": c.title or "",
        "description": c.description or "",
        "ci_type": c.ci_type or "",
        "asset_id": c.asset_id,
        "change_type": c.change_type or "normal",
        "priority": c.priority or "medium",
        "status": c.status or "draft",
        "risk_level": c.risk_level or "low",
        "planned_start": c.planned_start.strftime("%Y-%m-%d %H:%M") if c.planned_start else None,
        "planned_end": c.planned_end.strftime("%Y-%m-%d %H:%M") if c.planned_end else None,
        "requester_id": c.requester_id,
        "requester_name": requester.username if requester else "",
        "reviewer_id": c.reviewer_id,
        "reviewer_name": reviewer.username if reviewer else "",
        "review_comment": c.review_comment or "",
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else None,
        "updated_at": c.updated_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(c, "updated_at", None) else None,
    }


def _task_to_dict(t, users: dict) -> dict:
    executor = users.get(t.executed_by)
    return {
        "id": t.id,
        "change_id": t.change_id,
        "step_order": t.step_order or 0,
        "description": t.description or "",
        "command": t.command or "",
        "status": t.status or "pending",
        "result": t.result or "",
        "executed_by": t.executed_by,
        "executor_name": executor.username if executor else "",
        "executed_at": t.executed_at.strftime("%Y-%m-%d %H:%M:%S") if t.executed_at else None,
        "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else None,
    }


@router.get("/api/list")
def api_change_list(page: int = 1, per_page: int = 20, db: Session = Depends(get_db)):
    """变更审批列表 JSON API（分页）."""
    q = db.query(ChangeRequest).order_by(ChangeRequest.created_at.desc())
    total = q.count()
    changes = q.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    users = {u.id: u for u in db.query(User).all()}
    return JSONResponse({
        "changes": [_change_to_dict(c, users) for c in changes],
        "users": [{"id": u.id, "username": u.username} for u in users.values()],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    })


@router.post("/api/create")
def api_change_create(
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
    db: Session = Depends(get_db)):
    """创建变更 JSON API."""
    user_id = request.session.get("user_id")
    c = ChangeRequest(
        title=title, description=description, ci_type=ci_type,
        asset_id=asset_id if asset_id else None,
        change_type=change_type, priority=priority, risk_level=risk_level,
        requester_id=user_id,
        planned_start=datetime.fromisoformat(planned_start) if planned_start else None,
        planned_end=datetime.fromisoformat(planned_end) if planned_end else None)
    db.add(c)
    db.commit()
    db.refresh(c)
    return JSONResponse({"ok": True, "id": c.id})


@router.get("/api/{change_id}")
def api_change_detail(change_id: int, db: Session = Depends(get_db)):
    """变更详情 JSON API."""
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if not c:
        return JSONResponse({"error": "not found"}, status_code=404)
    tasks = db.query(ChangeTask).filter(ChangeTask.change_id == change_id).order_by(ChangeTask.step_order).all()
    users = {u.id: u for u in db.query(User).all()}
    return JSONResponse({
        "change": _change_to_dict(c, users),
        "tasks": [_task_to_dict(t, users) for t in tasks],
        "users": [{"id": u.id, "username": u.username} for u in users.values()],
    })


@router.post("/api/{change_id}/submit")
def api_change_submit(change_id: int, db: Session = Depends(get_db)):
    """提交审批 JSON API."""
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if not c:
        return JSONResponse({"error": "not found"}, status_code=404)
    if c.status != "draft":
        return JSONResponse({"ok": False, "error": f"当前状态为 {c.status}，仅 draft 状态可提交审批", "status": c.status})
    c.status = "pending_approval"
    db.commit()
    return JSONResponse({"ok": True, "status": c.status})


@router.post("/api/{change_id}/approve")
def api_change_approve(
    change_id: int, request: Request,
    review_comment: str = Form(""),
    db: Session = Depends(get_db)):
    """审批通过 JSON API."""
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if not c:
        return JSONResponse({"error": "not found"}, status_code=404)
    if c.status != "pending_approval":
        return JSONResponse({"ok": False, "error": f"当前状态为 {c.status}，仅 pending_approval 状态可审批通过", "status": c.status})
    c.status = "approved"
    c.reviewer_id = request.session.get("user_id")
    c.review_comment = review_comment
    db.commit()
    return JSONResponse({"ok": True, "status": c.status})


@router.post("/api/{change_id}/reject")
def api_change_reject(
    change_id: int, request: Request,
    review_comment: str = Form(""),
    db: Session = Depends(get_db)):
    """审批驳回 JSON API."""
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if not c:
        return JSONResponse({"error": "not found"}, status_code=404)
    if c.status != "pending_approval":
        return JSONResponse({"ok": False, "error": f"当前状态为 {c.status}，仅 pending_approval 状态可驳回", "status": c.status})
    c.status = "rejected"
    c.reviewer_id = request.session.get("user_id")
    c.review_comment = review_comment
    db.commit()
    return JSONResponse({"ok": True, "status": c.status})


@router.post("/api/{change_id}/start")
def api_change_start(change_id: int, db: Session = Depends(get_db)):
    """开始执行 JSON API."""
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if not c:
        return JSONResponse({"error": "not found"}, status_code=404)
    if c.status not in ("approved", "in_progress"):
        return JSONResponse({"ok": False, "error": f"当前状态为 {c.status}，仅 approved 状态可开始执行", "status": c.status})
    c.status = "in_progress"
    db.commit()
    return JSONResponse({"ok": True, "status": c.status})


@router.post("/api/{change_id}/complete")
def api_change_complete(change_id: int, db: Session = Depends(get_db)):
    """完成变更 JSON API."""
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if not c:
        return JSONResponse({"error": "not found"}, status_code=404)
    if c.status != "in_progress":
        return JSONResponse({"ok": False, "error": f"当前状态为 {c.status}，仅 in_progress 状态可完成", "status": c.status})
    c.status = "completed"
    db.commit()
    return JSONResponse({"ok": True, "status": c.status})


@router.post("/api/{change_id}/rollback")
def api_change_rollback(change_id: int, db: Session = Depends(get_db)):
    """回滚变更 JSON API."""
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if not c:
        return JSONResponse({"error": "not found"}, status_code=404)
    if c.status not in ("approved", "in_progress"):
        return JSONResponse({"ok": False, "error": f"当前状态为 {c.status}，仅 approved/in_progress 状态可回滚", "status": c.status})
    c.status = "rolled_back"
    db.commit()
    return JSONResponse({"ok": True, "status": c.status})


@router.post("/api/{change_id}/tasks/new")
def api_task_new(
    change_id: int,
    description: str = Form(...),
    command: str = Form(""),
    step_order: int = Form(0),
    db: Session = Depends(get_db)):
    """新增执行步骤 JSON API."""
    c = db.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
    if not c:
        return JSONResponse({"error": "not found"}, status_code=404)
    t = ChangeTask(change_id=change_id, description=description, command=command, step_order=step_order)
    db.add(t)
    db.commit()
    db.refresh(t)
    return JSONResponse({"ok": True, "id": t.id})


@router.post("/api/{change_id}/tasks/{task_id}/status")
def api_task_update_status(
    change_id: int, task_id: int,
    request: Request,
    status: str = Form(...),
    result: str = Form(""),
    db: Session = Depends(get_db)):
    """更新执行步骤状态 JSON API."""
    t = db.query(ChangeTask).filter(ChangeTask.id == task_id, ChangeTask.change_id == change_id).first()
    if not t:
        return JSONResponse({"error": "not found"}, status_code=404)
    t.status = status
    t.result = result
    t.executed_by = request.session.get("user_id")
    if status in ("completed", "failed"):
        t.executed_at = datetime.now()
    db.commit()
    return JSONResponse({"ok": True, "status": t.status})


# ─── HTML 路由（fallback）───

