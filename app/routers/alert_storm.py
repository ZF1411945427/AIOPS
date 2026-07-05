from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AlertSuppression, SystemConfig, AlertRule
from app.services import alert_service
from app.template_utils import get_templates

router = APIRouter(prefix="/alert-storm", tags=["alert_storm"])
templates = get_templates()


