from fastapi import APIRouter, Depends, Request, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import Span
from app.template_utils import get_templates

router = APIRouter(prefix="/traces", tags=["traces"])
templates = get_templates()


@router.post("/ingest")
def ingest_span(
    trace_id: str = Form(...), span_id: str = Form(...),
    parent_span_id: str = Form(""), service_name: str = Form(...),
    operation_name: str = Form(...), duration_ms: float = Form(0),
    status: str = Form("OK"), tags: str = Form("{}"),
    db: Session = Depends(get_db)):
    from datetime import datetime
    span = Span(
        trace_id=trace_id, span_id=span_id, parent_span_id=parent_span_id,
        service_name=service_name, operation_name=operation_name,
        start_time=datetime.now(), end_time=datetime.now(),
        duration_ms=duration_ms, status=status, tags=tags)
    db.add(span)
    db.commit()
    return {"ok": True, "span_id": span.id}

