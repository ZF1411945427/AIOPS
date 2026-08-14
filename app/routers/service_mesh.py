from fastapi import APIRouter
from app.template_utils import get_templates

router = APIRouter(prefix="/service-mesh", tags=["service-mesh"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "service_mesh", "status": "ok"}


