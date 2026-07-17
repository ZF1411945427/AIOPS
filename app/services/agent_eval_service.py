import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, Integer, Float
from app.models import AgentEvaluation, ChatSession, ChatMessage, ToolInvocation


def record_evaluation(
    db: Session,
    session_id: int = None,
    provider_id: int = None,
    model_name: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    latency_ms: int = 0,
    round_count: int = 0,
    tool_call_count: int = 0,
    success: bool = True,
    has_hallucination: bool = False,
    completion_rate: float = 1.0,
    feedback: str = "",
) -> int:
    ev = AgentEvaluation(
        session_id=session_id,
        provider_id=provider_id,
        model_name=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        round_count=round_count,
        tool_call_count=tool_call_count,
        is_success=success,
        has_hallucination=has_hallucination,
        completion_rate=completion_rate,
        feedback=feedback,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev.id


def get_eval_stats(db: Session, days: int = 30) -> dict:
    since = datetime.now() - timedelta(days=days)

    total = db.query(func.count(AgentEvaluation.id)).filter(
        AgentEvaluation.created_at >= since
    ).scalar() or 0

    success_count = db.query(func.count(AgentEvaluation.id)).filter(
        AgentEvaluation.created_at >= since,
        AgentEvaluation.is_success == True,
    ).scalar() or 0

    hallucination_count = db.query(func.count(AgentEvaluation.id)).filter(
        AgentEvaluation.created_at >= since,
        AgentEvaluation.has_hallucination == True,
    ).scalar() or 0

    avg_latency = db.query(func.avg(AgentEvaluation.latency_ms)).filter(
        AgentEvaluation.created_at >= since,
    ).scalar() or 0

    avg_tokens = db.query(func.avg(AgentEvaluation.total_tokens)).filter(
        AgentEvaluation.created_at >= since,
    ).scalar() or 0

    avg_round = db.query(func.avg(AgentEvaluation.round_count)).filter(
        AgentEvaluation.created_at >= since,
    ).scalar() or 0

    avg_tool_calls = db.query(func.avg(AgentEvaluation.tool_call_count)).filter(
        AgentEvaluation.created_at >= since,
    ).scalar() or 0

    sessions_total = db.query(func.count(ChatSession.id)).filter(
        ChatSession.created_at >= since,
    ).scalar() or 0

    tools_q = db.query(
        ToolInvocation.tool_name,
        func.count(ToolInvocation.id).label("count"),
        func.sum(func.cast(ToolInvocation.status == "success", Integer)).label("is_success"),
        func.avg(ToolInvocation.latency_ms).label("avg_latency"),
    ).filter(ToolInvocation.created_at >= since).group_by(ToolInvocation.tool_name).all()

    daily_rows = db.query(
        func.date(AgentEvaluation.created_at).label("date"),
        func.count(AgentEvaluation.id).label("count"),
        func.avg(func.cast(AgentEvaluation.is_success, Float)).label("avg_success"),
    ).filter(
        AgentEvaluation.created_at >= since
    ).group_by(
        func.date(AgentEvaluation.created_at)
    ).order_by(
        func.date(AgentEvaluation.created_at)
    ).all()

    return {
        "total_sessions": sessions_total,
        "total_evals": total,
        "success_count": success_count,
        "hallucination_count": hallucination_count,
        "success_rate": round(success_count / max(total, 1) * 100, 1),
        "hallucination_rate": round(hallucination_count / max(total, 1) * 100, 1),
        "avg_latency_ms": round(float(avg_latency or 0), 1),
        "avg_tokens": round(float(avg_tokens or 0), 1),
        "avg_round_count": round(float(avg_round or 0), 1),
        "avg_tool_calls": round(float(avg_tool_calls or 0), 1),
        "period_days": days,
        "tools": [
            {
                "tool_name": t.tool_name,
                "count": t.count,
                "is_success": int(t.is_success or 0),
                "success_rate": round(int(t.is_success or 0) / max(t.count, 1) * 100, 1),
                "avg_latency_ms": round(float(t.avg_latency or 0), 1),
            }
            for t in tools_q
        ] if tools_q else [],
        "daily_trend": [
            {
                "date": str(t.date),
                "count": t.count,
                "success_rate": round(float(t.avg_success or 0) * 100, 1),
            }
            for t in daily_rows
        ] if daily_rows else [],
    }


def get_eval_history(db: Session, page: int = 1, per_page: int = 20):
    q = db.query(AgentEvaluation).order_by(AgentEvaluation.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return items, total
