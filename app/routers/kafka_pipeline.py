from fastapi import APIRouter
from app.template_utils import get_templates

router = APIRouter(prefix="/kafka", tags=["kafka"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "kafka_pipeline", "status": "ok"}


