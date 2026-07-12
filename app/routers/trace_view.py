from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Asset, AssetRelation
from app.services import topology_service
from app.template_utils import get_templates

router = APIRouter(prefix="/trace-view", tags=["trace_view"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "trace_view", "status": "ok"}


