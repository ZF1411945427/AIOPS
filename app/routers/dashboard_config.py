import json
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import DashboardCardConfig, User
from app.routers.auth import get_current_user
from app.template_utils import get_templates

router = APIRouter(prefix="/dashboard-config", tags=["dashboard_config"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "dashboard_config", "status": "ok"}


