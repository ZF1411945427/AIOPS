import json
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import SavedFilter, Alert, AlertRule, AlertEventLink, K8sEvent
from app.template_utils import get_templates

router = APIRouter(prefix="/alert-console", tags=["alert_console"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "alert_console", "status": "ok"}


