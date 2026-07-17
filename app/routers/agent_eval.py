from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import agent_eval_service

router = APIRouter(prefix="/agent/api/eval", tags=["agent_eval"])


def _eval_to_dict(e):
    return {
        "id": e.id,
        "session_id": e.session_id,
        "provider_id": e.provider_id,
        "model_name": e.model_name,
        "task_type": e.task_type,
        "prompt_tokens": e.prompt_tokens,
        "completion_tokens": e.completion_tokens,
        "total_tokens": e.total_tokens,
        "latency_ms": e.latency_ms,
        "round_count": e.round_count,
        "tool_call_count": e.tool_call_count,
        "is_success": bool(e.is_success),
        "has_hallucination": bool(e.has_hallucination),
        "completion_rate": e.completion_rate,
        "feedback": e.feedback,
        "created_at": e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else None,
    }


@router.get("/stats")
def get_stats(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    stats = agent_eval_service.get_eval_stats(db, days=days)
    return JSONResponse(stats)


@router.get("/history")
def get_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items, total = agent_eval_service.get_eval_history(db, page=page, per_page=per_page)
    return JSONResponse({
        "items": [_eval_to_dict(e) for e in items],
        "total": total,
        "page": page,
        "per_page": per_page,
    })
