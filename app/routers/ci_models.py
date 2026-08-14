from fastapi import APIRouter
from app.template_utils import get_templates

router = APIRouter(prefix="/ci-models", tags=["ci_models"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "ci_models", "status": "ok"}


