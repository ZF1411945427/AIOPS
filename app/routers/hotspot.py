from fastapi import APIRouter
from app.template_utils import get_templates

router = APIRouter(prefix="/hotspot", tags=["hotspot"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "hotspot", "status": "ok"}


