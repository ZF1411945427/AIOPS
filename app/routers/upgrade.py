"""edge 升级任务 API(F5)。契约见 CONTRACT.md 20.5。"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.database import get_db
from app.services import upgrade_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/upgrade-jobs", tags=["upgrade"])


def _current_user_id(request: Request) -> int:
    uid = request.session.get("user_id")
    if not uid:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            try:
                from app.services.mobile_push_service import verify_login_token
                payload = verify_login_token(auth[7:])
                if payload:
                    uid = payload.get("user_id")
            except Exception as _exc:
                logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)
    return uid


@router.get("")
def api_job_list(request: Request, db: Session = Depends(get_db)):
    return JSONResponse({"ok": True, "jobs": upgrade_service.list_jobs(db)})


@router.get("/{job_id}")
def api_job_get(job_id: int, request: Request, db: Session = Depends(get_db)):
    job = upgrade_service.get_job(db, job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "任务不存在"}, status_code=404)
    data = upgrade_service._job_dict(job)
    data["steps"] = upgrade_service.list_steps(db, job_id)
    return JSONResponse({"ok": True, "job": data})


@router.post("")
def api_job_create(request: Request, payload: dict, db: Session = Depends(get_db)):
    try:
        job = upgrade_service.create_job(db, payload, created_by=_current_user_id(request))
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "job": upgrade_service._job_dict(job)})


@router.post("/{job_id}/run")
def api_job_run(job_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        job = upgrade_service.run_job(db, job_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": True, "job": upgrade_service._job_dict(job),
                         "steps": upgrade_service.list_steps(db, job_id)})


@router.post("/{job_id}/pause")
def api_job_pause(job_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        job = upgrade_service.pause_job(db, job_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": True, "job": upgrade_service._job_dict(job)})


@router.delete("/{job_id}")
def api_job_delete(job_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        upgrade_service.delete_job(db, job_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": True})


import logging
logger = logging.getLogger(__name__)
