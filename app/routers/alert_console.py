from fastapi import APIRouter
from app.template_utils import get_templates

router = APIRouter(prefix="/alert-console", tags=["alert_console"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "alert_console", "status": "ok"}


