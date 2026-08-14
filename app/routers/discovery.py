from fastapi import APIRouter
from app.template_utils import get_templates

router = APIRouter(prefix="/discovery", tags=["discovery"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "discovery", "status": "ok"}


