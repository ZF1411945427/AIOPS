from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import KafkaPipeline
from app.template_utils import get_templates

router = APIRouter(prefix="/kafka", tags=["kafka"])
templates = get_templates()


