from fastapi import APIRouter
from app.template_utils import get_templates

router = APIRouter(prefix="/granger", tags=["granger"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "granger", "status": "ok"}


