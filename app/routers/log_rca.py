from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Alert, MetricRecord, Asset, AssetRelation
from app.template_utils import get_templates

router = APIRouter(prefix="/log-rca", tags=["log-rca"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "log_rca", "status": "ok"}


