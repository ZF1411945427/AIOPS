from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
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

    total_duration = max(s.end_time for s in spans) - min(s.start_time for s in spans)
    total_duration_ms = total_duration.total_seconds() * 1000 if total_duration else 0

    # Find root span
    root_spans = children_of.get("root", [])
    if not root_spans:
        root_spans = [spans[0]]

    # Latency analysis: find spans with abnormal duration
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

    # Error propagation: find error spans and trace to root
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

    # Service ranking by total latency contribution
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

    # Root cause candidates
    root_causes = sorted(anomalies, key=lambda x: -x.get("z_score", 0))
    # Also include services with high error rate
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


