from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import Span, Alert
from app.template_utils import get_templates

router = APIRouter(prefix="/trace-rca", tags=["trace-rca"])
templates = get_templates()


def build_span_tree(spans: list) -> dict:
    children_of = defaultdict(list)
    span_map = {}
    for s in spans:
        span_map[s.span_id] = s
        pid = s.parent_span_id or "root"
        children_of[pid].append(s)
    return {"span_map": span_map, "children_of": children_of}


def analyze_trace_rca(spans: list) -> dict:
    tree = build_span_tree(spans)
    span_map = tree["span_map"]
    children_of = tree["children_of"]

    if not spans:
        return {"error": "No spans found"}

    total_duration = max(s.ended_at for s in spans) - min(s.started_at for s in spans)
    total_duration_ms = total_duration.total_seconds() * 1000 if total_duration else 0

    root_spans = children_of.get("root", [])
    if not root_spans:
        root_spans = [spans[0]]

    all_durations = [s.duration_ms for s in spans]
    avg_dur = sum(all_durations) / len(all_durations) if all_durations else 0
    std_dur = (sum((d - avg_dur) ** 2 for d in all_durations) / len(all_durations)) ** 0.5 or 1

    anomalies = []
    for s in spans:
        z = (s.duration_ms - avg_dur) / std_dur
        if z > 2:
            anomalies.append({
                "span_id": s.span_id,
                "service": s.service_name,
                "operation": s.operation_name,
                "duration_ms": s.duration_ms,
                "z_score": round(z, 2),
                "type": "latency",
            })
        if s.status != "OK":
            anomalies.append({
                "span_id": s.span_id,
                "service": s.service_name,
                "operation": s.operation_name,
                "duration_ms": s.duration_ms,
                "status": s.status,
                "type": "error",
            })

    error_spans = [s for s in spans if s.status != "OK"]
    error_paths = []
    for es in error_spans:
        path = [es]
        pid = es.parent_span_id
        while pid and pid in span_map:
            parent = span_map[pid]
            path.append(parent)
            pid = parent.parent_span_id
        error_paths.append(list(reversed(path)))

    service_stats = defaultdict(lambda: {"total_duration": 0, "call_count": 0, "error_count": 0, "avg_duration": 0})
    for s in spans:
        sv = service_stats[s.service_name]
        sv["total_duration"] += s.duration_ms
        sv["call_count"] += 1
        if s.status != "OK":
            sv["error_count"] += 1
    for sv in service_stats.values():
        sv["avg_duration"] = round(sv["total_duration"] / sv["call_count"], 1) if sv["call_count"] else 0
        sv["error_rate"] = round(sv["error_count"] / sv["call_count"] * 100, 1) if sv["call_count"] else 0

    sorted_services = sorted(service_stats.items(), key=lambda x: -x[1]["total_duration"])

    root_causes = sorted(anomalies, key=lambda x: -x.get("z_score", 0))
    for sv_name, sv in sorted_services:
        if sv["error_rate"] > 10:
            root_causes.append({
                "service": sv_name,
                "type": "high_error_rate",
                "error_rate": sv["error_rate"],
                "call_count": sv["call_count"],
            })

    return {
        "total_spans": len(spans),
        "total_duration_ms": round(total_duration_ms, 1),
        "services": sorted_services[:10],
        "anomalies": anomalies[:20],
        "error_paths": error_paths[:5],
        "root_causes": root_causes[:10],
        "avg_duration": round(avg_dur, 1),
    }


@router.get("/analyze")
def analyze_trace(
    db: Session = Depends(get_db),
    trace_id: str = Query(None, description="Trace ID"),
    hours: int = Query(1, description="最近 N 小时"),
):
    """链路追踪根因分析：对指定 trace 或最近 traces 做 RCA"""
    try:
        q = db.query(Span)
        if trace_id:
            q = q.filter(Span.trace_id == trace_id)
        else:
            since = datetime.now() - timedelta(hours=hours)
            q = q.filter(Span.started_at >= since).order_by(desc(Span.started_at)).limit(500)
        spans = q.all()
        if not spans:
            return JSONResponse({"error": "No spans found"}, status_code=404)
        result = analyze_trace_rca(spans)
        return result
    except Exception as e:
        from app.logger import logger
        logger.error(f"trace-rca analyze failed: {e}")
        return JSONResponse({"error": "分析失败"}, status_code=500)


@router.get("/traces")
def list_recent_traces(
    db: Session = Depends(get_db),
    hours: int = Query(1, description="最近 N 小时"),
    limit: int = Query(20, description="返回数量"),
):
    """列出最近的 trace（用于选择分析目标）"""
    try:
        since = datetime.now() - timedelta(hours=hours)
        rows = (
            db.query(Span.trace_id, Span.service_name, Span.started_at, Span.duration_ms, Span.status)
            .filter(Span.started_at >= since)
            .order_by(desc(Span.started_at))
            .limit(limit * 10)
            .all()
        )
        seen = {}
        for r in rows:
            tid = r[0]
            if tid not in seen:
                seen[tid] = {
                    "trace_id": tid,
                    "first_service": r[1],
                    "start_time": r[2].isoformat() if r[2] else "",
                    "duration_ms": r[3],
                    "status": r[4],
                }
        return {"traces": list(seen.values())[:limit]}
    except Exception as e:
        from app.logger import logger
        logger.error(f"trace-rca list failed: {e}")
        return JSONResponse({"error": "查询失败"}, status_code=500)
