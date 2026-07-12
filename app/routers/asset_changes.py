from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.asset_change_service import get_change_logs
from app.template_utils import get_templates

router = APIRouter(prefix="/asset-changes", tags=["asset_changes"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "asset_changes", "status": "ok"}


