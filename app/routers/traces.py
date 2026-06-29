from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import Span
from app.template_utils import get_templates

router = APIRouter(prefix="/traces", tags=["traces"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def trace_list(request: Request, db: Session = Depends(get_db)):
    services = [r[0] for r in db.query(Span.service_name).distinct().all()]
    operations = [r[0] for r in db.query(Span.operation_name).distinct().all()]
    trace_ids = [r[0] for r in db.query(Span.trace_id).distinct().order_by(desc(Span.trace_id)).limit(100).all()]
    return templates.TemplateResponse("traces.html", {
        "request": request, "services": services, "operations": operations,
        "trace_ids": trace_ids, "spans": None,
    })


@router.post("/query", response_class=HTMLResponse)
def trace_query(
    request: Request, service_name: str = Form(""), operation_name: str = Form(""),
    trace_id: str = Form(""), min_duration: float = Form(0), max_duration: float = Form(0),
    limit: int = Form(100), db: Session = Depends(get_db),
):
    q = db.query(Span)
    if service_name:
        q = q.filter(Span.service_name == service_name)
    if operation_name:
        q = q.filter(Span.operation_name == operation_name)
    if trace_id:
        q = q.filter(Span.trace_id == trace_id)
    if min_duration > 0:
        q = q.filter(Span.duration_ms >= min_duration)
    if max_duration > 0:
        q = q.filter(Span.duration_ms <= max_duration)
    spans = q.order_by(desc(Span.start_time)).limit(limit).all()
    services = [r[0] for r in db.query(Span.service_name).distinct().all()]
    operations = [r[0] for r in db.query(Span.operation_name).distinct().all()]
    trace_ids = [r[0] for r in db.query(Span.trace_id).distinct().order_by(desc(Span.trace_id)).limit(100).all()]
    return templates.TemplateResponse("traces.html", {
        "request": request, "services": services, "operations": operations,
        "trace_ids": trace_ids, "spans": spans,
    })


@router.get("/detail/{trace_id}", response_class=HTMLResponse)
def trace_detail(trace_id: str, request: Request, db: Session = Depends(get_db)):
    spans = db.query(Span).filter(Span.trace_id == trace_id).order_by(Span.start_time).all()
    return templates.TemplateResponse("trace_detail.html", {
        "request": request, "trace_id": trace_id, "spans": spans,
    })


@router.post("/ingest")
def ingest_span(
    trace_id: str = Form(...), span_id: str = Form(...),
    parent_span_id: str = Form(""), service_name: str = Form(...),
    operation_name: str = Form(...), duration_ms: float = Form(0),
    status: str = Form("OK"), tags: str = Form("{}"),
    db: Session = Depends(get_db),
):
    from datetime import datetime
    span = Span(
        trace_id=trace_id, span_id=span_id, parent_span_id=parent_span_id,
        service_name=service_name, operation_name=operation_name,
        start_time=datetime.now(), end_time=datetime.now(),
        duration_ms=duration_ms, status=status, tags=tags,
    )
    db.add(span)
    db.commit()
    return {"ok": True, "span_id": span.id}

