from fastapi import APIRouter
from app.template_utils import get_templates

router = APIRouter(prefix="/alert-silence", tags=["alert_silence"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "alert_silence", "status": "ok"}


