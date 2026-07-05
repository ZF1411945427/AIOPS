import json
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.database import get_db
from app.models import Span

router = APIRouter(prefix="/api/traces", tags=["api_traces"])


@router.get("")
def list_traces(
    service: str = Query(""), operation: str = Query(""),
    keyword: str = Query(""), status: str = Query(""),
    min_dur: float = Query(0), max_dur: float = Query(0),
    limit: int = Query(50), offset: int = Query(0),
    db: Session = Depends(get_db)):
    """查询调用链列表 — 从真实 Span 数据查询，不再生成随机种子数据"""
    # 聚合每个 trace_id 的统计信息
    subq = db.query(
        Span.trace_id,
        func.count(Span.id).label("span_count"),
        func.sum(Span.duration_ms).label("total_dur"),
        func.min(Span.start_time).label("root_time"),
        func.max(Span.status).label("worst_status")).group_by(Span.trace_id)

    # 过滤
    if service:
        subq = subq.having(Span.service_name == service)
    if min_dur > 0:
        subq = subq.having(func.avg(Span.duration_ms) >= min_dur)
    if max_dur > 0:
        subq = subq.having(func.avg(Span.duration_ms) <= max_dur)
    if status:
        subq = subq.having(Span.status == status)
    if keyword:
        subq = subq.having(
            Span.service_name.ilike(f"%{keyword}%")
            | Span.operation_name.ilike(f"%{keyword}%")
            | Span.trace_id.ilike(f"%{keyword}%")
        )

    subq = subq.order_by(desc(func.min(Span.start_time))).limit(limit).offset(offset)
    rows = subq.all()

    # 获取所有服务列表
    services = [r[0] for r in db.query(Span.service_name).distinct().order_by(Span.service_name).all() if r[0]]

    results = []
    for r in rows:
        # 找 root span
        root = db.query(Span).filter(
            Span.trace_id == r.trace_id,
            Span.parent_span_id == ""
        ).first()
        if not root:
            root = db.query(Span).filter(Span.trace_id == r.trace_id).order_by(Span.start_time).first()

        results.append({
            "trace_id": r.trace_id,
            "span_count": r.span_count,
            "total_duration_ms": round(r.total_dur or 0, 1),
            "root_service": root.service_name if root else "",
            "root_operation": root.operation_name if root else "",
            "start_time": r.root_time.strftime("%Y-%m-%d %H:%M:%S") if r.root_time else "",
            "worst_status": r.worst_status or "OK",
        })

    total = db.query(Span.trace_id).distinct().count()
    return JSONResponse({"traces": results, "services": services, "total": total})


@router.get("/{trace_id}")
def get_trace(trace_id: str, db: Session = Depends(get_db)):
    """获取单个调用链的完整 Span 详情"""
    spans = db.query(Span).filter(Span.trace_id == trace_id).order_by(Span.start_time).all()
    if not spans:
        return JSONResponse({"spans": []})

    root_span = None
    for s in spans:
        if not s.parent_span_id:
            root_span = s
            break
    if not root_span:
        root_span = spans[0]

    root_start = root_span.start_time
    root_end = root_span.end_time
    root_dur = (root_end - root_start).total_seconds() * 1000 if root_end and root_start else 0
    if root_dur <= 0:
        root_dur = 1

    span_list = []
    for s in spans:
        tags = s.tags
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = {}
        span_list.append({
            "span_id": s.span_id,
            "parent_span_id": s.parent_span_id or "",
            "service_name": s.service_name,
            "operation_name": s.operation_name,
            "start_time": s.start_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if s.start_time else "",
            "duration_ms": s.duration_ms,
            "status": s.status,
            "tags": tags,
        })

    services = list(set(s["service_name"] for s in span_list if s["service_name"]))

    # 构建拓扑边
    edges = []
    span_id_to_service = {s["span_id"]: s["service_name"] for s in span_list}
    for s in span_list:
        if s["parent_span_id"]:
            parent_svc = span_id_to_service.get(s["parent_span_id"])
            if parent_svc and parent_svc != s["service_name"]:
                edge_key = f"{parent_svc}->{s['service_name']}"
                if edge_key not in [f"{e['source']}->{e['target']}" for e in edges]:
                    edges.append({"source": parent_svc, "target": s["service_name"]})

    return JSONResponse({
        "trace_id": trace_id,
        "total_spans": len(spans),
        "root_duration_ms": round(root_dur, 1),
        "root_start": root_start.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if root_start else "",
        "services": services,
        "spans": span_list,
        "topology": {"services": services, "edges": edges},
    })
