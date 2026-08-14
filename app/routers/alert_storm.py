from fastapi import APIRouter
from app.template_utils import get_templates

router = APIRouter(prefix="/alert-storm", tags=["alert_storm"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "alert_storm", "status": "ok"}


