from fastapi import APIRouter
from app.template_utils import get_templates


router = APIRouter(prefix="/api-tokens", tags=["api-tokens"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "tokens", "status": "ok"}


