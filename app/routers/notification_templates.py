from fastapi import APIRouter

router = APIRouter(prefix="/notification-templates", tags=["notification_templates"])


@router.get("/status")
def status():
    return {"module": "notification_templates", "status": "ok"}
