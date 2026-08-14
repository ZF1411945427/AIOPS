from fastapi import APIRouter

from app.template_utils import get_templates

router = APIRouter(prefix="/predictions", tags=["predictions"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "predictions", "status": "ok"}


