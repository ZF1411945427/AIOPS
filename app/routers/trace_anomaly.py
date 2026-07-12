from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import TraceAnomalyConfig, Span
from app.template_utils import get_templates

router = APIRouter(prefix="/trace-anomaly", tags=["trace-anomaly"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "trace_anomaly", "status": "ok"}


