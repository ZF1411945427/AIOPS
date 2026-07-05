from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AlertSilenceSchedule
from app.template_utils import get_templates

router = APIRouter(prefix="/alert-silence", tags=["alert_silence"])
templates = get_templates()


