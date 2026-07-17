from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, case, extract

from app.database import get_db
from app.models import (
    Alert, Incident, RemediationLog,
    ToolInvocation, AgentEvaluation, NotificationLog,
)

router = APIRouter(prefix="/api/ops-analytics", tags=["ops-analytics"])


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    now = datetime.now()
    day30 = now - timedelta(days=30)
    day7 = now - timedelta(days=7)
    day1 = now - timedelta(days=1)

    total_alerts_30d = db.query(func.count(Alert.id)).filter(Alert.created_at >= day30).scalar() or 0
    total_alerts_7d = db.query(func.count(Alert.id)).filter(Alert.created_at >= day7).scalar() or 0
    total_alerts_1d = db.query(func.count(Alert.id)).filter(Alert.created_at >= day1).scalar() or 0
    resolved_alerts_30d = db.query(func.count(Alert.id)).filter(
        Alert.created_at >= day30, Alert.status == "resolved"
    ).scalar() or 0
    active_alerts = db.query(func.count(Alert.id)).filter(
        Alert.status.in_(["firing", "triggered"])
    ).scalar() or 0

    total_incidents_30d = db.query(func.count(Incident.id)).filter(Incident.created_at >= day30).scalar() or 0
    resolved_incidents_30d = db.query(func.count(Incident.id)).filter(
        Incident.created_at >= day30, Incident.status == "resolved"
    ).scalar() or 0
    open_incidents = db.query(func.count(Incident.id)).filter(
        Incident.status.in_(["open", "pending_approval"])
    ).scalar() or 0

    total_remediations_30d = db.query(func.count(RemediationLog.id)).filter(RemediationLog.created_at >= day30).scalar() or 0
    success_remediations_30d = db.query(func.count(RemediationLog.id)).filter(
        RemediationLog.created_at >= day30, RemediationLog.is_success == True
    ).scalar() or 0

    total_tool_calls_30d = db.query(func.count(ToolInvocation.id)).filter(ToolInvocation.created_at >= day30).scalar() or 0
    success_tool_calls_30d = db.query(func.count(ToolInvocation.id)).filter(
        ToolInvocation.created_at >= day30, ToolInvocation.status == "success"
    ).scalar() or 0

    total_agent_evals_30d = db.query(func.count(AgentEvaluation.id)).filter(AgentEvaluation.created_at >= day30).scalar() or 0

    return JSONResponse({
        "alerts": {
            "total_30d": total_alerts_30d,
            "total_7d": total_alerts_7d,
            "total_1d": total_alerts_1d,
            "resolved_30d": resolved_alerts_30d,
            "active": active_alerts,
        },
        "incidents": {
            "total_30d": total_incidents_30d,
            "resolved_30d": resolved_incidents_30d,
            "open": open_incidents,
        },
        "remediation": {
            "total_30d": total_remediations_30d,
            "success_30d": success_remediations_30d,
            "success_rate": round(success_remediations_30d / total_remediations_30d * 100, 1) if total_remediations_30d else 0,
        },
        "ai": {
            "tool_calls_30d": total_tool_calls_30d,
            "tool_success_30d": success_tool_calls_30d,
            "tool_success_rate": round(success_tool_calls_30d / total_tool_calls_30d * 100, 1) if total_tool_calls_30d else 0,
            "agent_evals_30d": total_agent_evals_30d,
        },
    })


@router.get("/mtta-mttr")
def mtta_mttr(db: Session = Depends(get_db), days: int = Query(30, ge=1, le=90)):
    now = datetime.now()
    since = now - timedelta(days=days)

    alerts = db.query(Alert).filter(
        Alert.created_at >= since,
    ).all()

    mtta_values = []
    mttr_values = []
    for a in alerts:
        if a.acknowledged_at and a.created_at:
            delta_sec = (a.acknowledged_at - a.created_at).total_seconds()
            if delta_sec >= 0:
                mtta_values.append(delta_sec)
        if a.resolved_at and a.created_at:
            delta_sec = (a.resolved_at - a.created_at).total_seconds()
            if delta_sec >= 0:
                mttr_values.append(delta_sec)

    incidents = db.query(Incident).filter(
        Incident.created_at >= since,
        Incident.resolved_at.isnot(None),
    ).all()
    for inc in incidents:
        if inc.resolved_at and inc.created_at:
            delta_sec = (inc.resolved_at - inc.created_at).total_seconds()
            mttr_values.append(delta_sec)

    avg_mtta = round(sum(mtta_values) / len(mtta_values) / 60, 1) if mtta_values else 0
    avg_mttr = round(sum(mttr_values) / len(mttr_values) / 60, 1) if mttr_values else 0

    daily_data = []
    for i in range(min(days, 30)):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_alerts = [a for a in alerts if day_start <= a.created_at < day_end]
        day_count = len(day_alerts)
        day_mtta = 0
        day_mttr = 0
        if day_count > 0:
            day_mtta_vals = [
                (a.acknowledged_at - a.created_at).total_seconds() / 60
                for a in day_alerts
                if a.acknowledged_at and a.created_at
            ]
            day_mttr_vals = [
                (a.resolved_at - a.created_at).total_seconds() / 60
                for a in day_alerts
                if a.resolved_at and a.created_at
            ]
            day_mtta = round(sum(day_mtta_vals) / len(day_mtta_vals), 1) if day_mtta_vals else 0
            day_mttr = round(sum(day_mttr_vals) / len(day_mttr_vals), 1) if day_mttr_vals else 0
        daily_data.append({
            "date": day_start.strftime("%m-%d"),
            "count": day_count,
            "mtta_min": day_mtta,
            "mttr_min": day_mttr,
        })
    daily_data.reverse()

    return JSONResponse({
        "avg_mtta_min": avg_mtta,
        "avg_mttr_min": avg_mttr,
        "acknowledged_count": len(mtta_values),
        "resolved_count": len(mttr_values),
        "daily": daily_data,
    })


@router.get("/alert-trend")
def alert_trend(db: Session = Depends(get_db), days: int = Query(30, ge=1, le=90)):
    now = datetime.now()
    dates = []
    critical_data = []
    warning_data = []
    info_data = []
    resolved_data = []

    for i in range(days, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        dates.append(day.strftime("%m-%d"))

        for sev, arr in [("critical", critical_data), ("warning", warning_data), ("info", info_data)]:
            cnt = db.query(func.count(Alert.id)).filter(
                Alert.created_at >= day_start,
                Alert.created_at < day_end,
                Alert.severity == sev,
            ).scalar() or 0
            arr.append(cnt)

        res_cnt = db.query(func.count(Alert.id)).filter(
            Alert.resolved_at >= day_start,
            Alert.resolved_at < day_end,
        ).scalar() or 0
        resolved_data.append(res_cnt)

    return JSONResponse({
        "dates": dates,
        "critical": critical_data,
        "warning": warning_data,
        "info": info_data,
        "resolved": resolved_data,
    })


@router.get("/remediation-effect")
def remediation_effect_stats(db: Session = Depends(get_db), days: int = Query(30, ge=1, le=90)):
    now = datetime.now()
    since = now - timedelta(days=days)

    total = db.query(func.count(RemediationLog.id)).filter(RemediationLog.created_at >= since).scalar() or 0
    success = db.query(func.count(RemediationLog.id)).filter(
        RemediationLog.created_at >= since, RemediationLog.is_success == True
    ).scalar() or 0

    action_dist = db.query(
        RemediationLog.action_type, func.count(RemediationLog.id)
    ).filter(RemediationLog.created_at >= since).group_by(RemediationLog.action_type).all()

    daily_data = []
    for i in range(min(days, 30)):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_total = db.query(func.count(RemediationLog.id)).filter(
            RemediationLog.created_at >= day_start, RemediationLog.created_at < day_end
        ).scalar() or 0
        day_success = db.query(func.count(RemediationLog.id)).filter(
            RemediationLog.created_at >= day_start, RemediationLog.created_at < day_end,
            RemediationLog.is_success == True
        ).scalar() or 0
        daily_data.append({
            "date": day_start.strftime("%m-%d"),
            "total": day_total,
            "success": day_success,
        })
    daily_data.reverse()

    return JSONResponse({
        "total": total,
        "recovered": success,
        "alert_resolved": success,
        "recovery_rate": round(success / total * 100, 1) if total else 0,
        "avg_recovery_sec": 0,
        "action_distribution": [{"action": a, "count": c} for a, c in action_dist],
        "daily": daily_data,
    })


@router.get("/ai-efficiency")
def ai_efficiency(db: Session = Depends(get_db), days: int = Query(30, ge=1, le=90)):
    now = datetime.now()
    since = now - timedelta(days=days)

    total_evals = db.query(func.count(AgentEvaluation.id)).filter(AgentEvaluation.created_at >= since).scalar() or 0
    success_evals = db.query(func.count(AgentEvaluation.id)).filter(
        AgentEvaluation.created_at >= since, AgentEvaluation.is_success == True
    ).scalar() or 0
    hallucination_count = db.query(func.count(AgentEvaluation.id)).filter(
        AgentEvaluation.created_at >= since, AgentEvaluation.has_hallucination == True
    ).scalar() or 0

    avg_latency = db.query(func.avg(AgentEvaluation.latency_ms)).filter(AgentEvaluation.created_at >= since).scalar() or 0
    avg_rounds = db.query(func.avg(AgentEvaluation.round_count)).filter(AgentEvaluation.created_at >= since).scalar() or 0
    avg_completion = db.query(func.avg(AgentEvaluation.completion_rate)).filter(AgentEvaluation.created_at >= since).scalar() or 0
    avg_tokens = db.query(func.avg(AgentEvaluation.total_tokens)).filter(AgentEvaluation.created_at >= since).scalar() or 0

    total_tool_calls = db.query(func.count(ToolInvocation.id)).filter(ToolInvocation.created_at >= since).scalar() or 0
    success_tool_calls = db.query(func.count(ToolInvocation.id)).filter(
        ToolInvocation.created_at >= since, ToolInvocation.status == "success"
    ).scalar() or 0
    avg_tool_latency = db.query(func.avg(ToolInvocation.latency_ms)).filter(ToolInvocation.created_at >= since).scalar() or 0

    tool_dist = db.query(
        ToolInvocation.tool_name, func.count(ToolInvocation.id)
    ).filter(ToolInvocation.created_at >= since).group_by(ToolInvocation.tool_name).order_by(func.count(ToolInvocation.id).desc()).limit(15).all()

    daily_eval = []
    for i in range(min(days, 30)):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_total = db.query(func.count(AgentEvaluation.id)).filter(
            AgentEvaluation.created_at >= day_start, AgentEvaluation.created_at < day_end
        ).scalar() or 0
        day_success = db.query(func.count(AgentEvaluation.id)).filter(
            AgentEvaluation.created_at >= day_start, AgentEvaluation.created_at < day_end,
            AgentEvaluation.is_success == True
        ).scalar() or 0
        daily_eval.append({
            "date": day_start.strftime("%m-%d"),
            "total": day_total,
            "success": day_success,
        })
    daily_eval.reverse()

    return JSONResponse({
        "agent": {
            "total_evals": total_evals,
            "success_evals": success_evals,
            "success_rate": round(success_evals / total_evals * 100, 1) if total_evals else 0,
            "hallucination_count": hallucination_count,
            "hallucination_rate": round(hallucination_count / total_evals * 100, 1) if total_evals else 0,
            "avg_latency_ms": round(avg_latency, 0) if avg_latency else 0,
            "avg_rounds": round(avg_rounds, 1) if avg_rounds else 0,
            "avg_completion": round(avg_completion * 100, 1) if avg_completion else 0,
            "avg_tokens": round(avg_tokens, 0) if avg_tokens else 0,
        },
        "tools": {
            "total_calls": total_tool_calls,
            "success_calls": success_tool_calls,
            "success_rate": round(success_tool_calls / total_tool_calls * 100, 1) if total_tool_calls else 0,
            "avg_latency_ms": round(avg_tool_latency, 0) if avg_tool_latency else 0,
            "top_tools": [{"name": n, "count": c} for n, c in tool_dist],
        },
        "daily": daily_eval,
    })


@router.get("/notification-stats")
def notification_stats(db: Session = Depends(get_db), days: int = Query(30, ge=1, le=90)):
    now = datetime.now()
    since = now - timedelta(days=days)

    total = db.query(func.count(NotificationLog.id)).filter(NotificationLog.created_at >= since).scalar() or 0
    success = db.query(func.count(NotificationLog.id)).filter(
        NotificationLog.created_at >= since, NotificationLog.is_success == True
    ).scalar() or 0

    channel_dist = db.query(
        NotificationLog.channel_type, func.count(NotificationLog.id)
    ).filter(NotificationLog.created_at >= since).group_by(NotificationLog.channel_type).all()

    daily_data = []
    for i in range(min(days, 30)):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_total = db.query(func.count(NotificationLog.id)).filter(
            NotificationLog.created_at >= day_start, NotificationLog.created_at < day_end
        ).scalar() or 0
        day_success = db.query(func.count(NotificationLog.id)).filter(
            NotificationLog.created_at >= day_start, NotificationLog.created_at < day_end,
            NotificationLog.is_success == True
        ).scalar() or 0
        daily_data.append({
            "date": day_start.strftime("%m-%d"),
            "total": day_total,
            "success": day_success,
        })
    daily_data.reverse()

    return JSONResponse({
        "total": total,
        "success": success,
        "success_rate": round(success / total * 100, 1) if total else 0,
        "channel_distribution": [{"channel": c, "count": cnt} for c, cnt in channel_dist],
        "daily": daily_data,
    })
