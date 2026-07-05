from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import MetricRecord, Asset
from app.services.dtw_service import find_similar_metrics
from app.template_utils import get_templates

router = APIRouter(prefix="/dtw", tags=["dtw"])
templates = get_templates()


