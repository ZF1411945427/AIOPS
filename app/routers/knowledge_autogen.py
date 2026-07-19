import json
import logging
from fastapi import APIRouter, Depends, Query, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import knowledge_autogen_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge/api/auto-gen", tags=["knowledge_autogen"])


def _draft_to_dict(d):
    sop_steps = []
    try:
        sop_steps = json.loads(d.sop_steps or "[]")
    except (json.JSONDecodeError, TypeError):
        sop_steps = []
    return {
        "id": d.id,
        "alert_id": d.alert_id,
        "title": d.title,
        "symptom": d.symptom,
        "root_cause": d.root_cause,
        "solution": d.solution,
        "tags": d.tags,
        "severity": d.severity,
        "asset_type": d.asset_type,
        "source_type": d.source_type or "auto",
        "sop_steps": sop_steps,
        "status": d.status,
        "reject_reason": d.reject_reason or "",
        "created_at": d.created_at.strftime("%Y-%m-%d %H:%M:%S") if d.created_at else None,
        "updated_at": d.updated_at.strftime("%Y-%m-%d %H:%M:%S") if d.updated_at else None,
    }


@router.post("/sop/incident/{incident_id}")
def generate_sop(incident_id: int, db: Session = Depends(get_db)):
    result = knowledge_autogen_service.generate_sop_from_incident(incident_id, db)
    if result.get("ok"):
        return JSONResponse({"ok": True, "draft_id": result.get("draft_id"), "title": result.get("title")})
    return JSONResponse({"ok": False, "error": result.get("error")}, status_code=400)


@router.post("/from-incident/{incident_id}")
def generate_from_incident(incident_id: int, db: Session = Depends(get_db)):
    """从故障单生成知识草稿（包含故障现象/根因/解决方案）"""
    result = knowledge_autogen_service.generate_from_incident(incident_id, db)
    if result.get("ok"):
        return JSONResponse({"ok": True, "draft_id": result.get("draft_id"), "title": result.get("title")})
    return JSONResponse({"ok": False, "error": result.get("error")}, status_code=400)


@router.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: int, db: Session = Depends(get_db)):
    result = knowledge_autogen_service.approve_draft(draft_id, db)
    if result.get("ok"):
        return JSONResponse({
            "ok": True,
            "kb_id": result.get("kb_id"),
            "linked_alerts": result.get("linked_alerts", []),
        })
    return JSONResponse({"ok": False, "error": result.get("error")}, status_code=400)


@router.post("/drafts/{draft_id}/reject")
def reject_draft(
    draft_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
):
    """拒绝草稿。reason 从 JSON body 读取，兼容旧的 Query 参数。"""
    reason = ""
    if isinstance(payload, dict):
        reason = (payload.get("reason") or "").strip()
    if not reason:
        reason = ""
    result = knowledge_autogen_service.reject_draft(draft_id, db, reason=reason)
    if result.get("ok"):
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "error": result.get("error")}, status_code=400)


@router.get("/drafts")
def list_drafts(
    status: str = Query("", description="过滤状态: pending/approved/rejected"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    drafts, total = knowledge_autogen_service.list_drafts(db, status=status, page=page, per_page=per_page)
    return JSONResponse({
        "items": [_draft_to_dict(d) for d in drafts],
        "total": total,
        "page": page,
        "per_page": per_page,
    })


@router.get("/drafts/stats")
def get_draft_stats(db: Session = Depends(get_db)):
    """草稿统计：后端一次 GROUP BY 完成各状态计数，避免前端 N+1 查询。"""
    stats = knowledge_autogen_service.get_draft_stats(db)
    return JSONResponse(stats)


@router.delete("/drafts/{draft_id}")
def delete_draft(draft_id: int, db: Session = Depends(get_db)):
    """删除草稿（仅允许删除非 approved 状态的草稿）"""
    result = knowledge_autogen_service.delete_draft(draft_id, db)
    if result.get("ok"):
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "error": result.get("error")}, status_code=400)


@router.post("/trigger/{alert_id}")
def trigger_generation(alert_id: int, db: Session = Depends(get_db)):
    result = knowledge_autogen_service.generate_draft(alert_id, db)
    if result.get("ok"):
        return JSONResponse({"ok": True, "draft_id": result.get("draft_id"), "title": result.get("title")})
    return JSONResponse({"ok": False, "error": result.get("error")}, status_code=400)
