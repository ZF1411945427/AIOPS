from fastapi import APIRouter

router = APIRouter(prefix="/report-schedules", tags=["report_schedules"])


@router.get("/status")
def status():
    return {"module": "report_schedules", "status": "ok"}
