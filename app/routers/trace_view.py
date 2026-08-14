from fastapi import APIRouter
from app.template_utils import get_templates

router = APIRouter(prefix="/trace-view", tags=["trace_view"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "trace_view", "status": "ok"}


