"""多集群 data plane API(F5)。契约见 CONTRACT.md 第二十章。"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.database import get_db
from app.services import multicluster_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/k8s-clusters", tags=["multicluster"])


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
def api_cluster_list(request: Request, db: Session = Depends(get_db)):
    return JSONResponse({
        "ok": True,
        "clusters": multicluster_service.cluster_summary(db),
        "roles": multicluster_service.CLUSTER_ROLES,
        "datasources": multicluster_service.available_datasources(db),
    })


@router.get("/{cluster_id}")
def api_cluster_get(cluster_id: int, db: Session = Depends(get_db)):
    try:
        detail = multicluster_service.cluster_telemetry(db, cluster_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": True, "cluster": detail})


@router.post("")
def api_cluster_create(request: Request, payload: dict, db: Session = Depends(get_db)):
    try:
        c = multicluster_service.create_cluster(db, payload, created_by=_current_user_id(request))
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "cluster": multicluster_service._cluster_dict(c)})


@router.put("/{cluster_id}")
def api_cluster_update(cluster_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    try:
        c = multicluster_service.update_cluster(db, cluster_id, payload)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": True, "cluster": multicluster_service._cluster_dict(c)})


@router.delete("/{cluster_id}")
def api_cluster_delete(cluster_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        multicluster_service.delete_cluster(db, cluster_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": True})


@router.post("/{cluster_id}/check")
def api_cluster_check(cluster_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        status = multicluster_service.check_cluster(db, cluster_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": True, "status": status})


import logging
logger = logging.getLogger(__name__)
