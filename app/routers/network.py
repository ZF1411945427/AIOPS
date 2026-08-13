"""网络设备管理 API(F6)。契约见 CONTRACT.md 第二十一章。"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.database import get_db
from app.services import network_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/network", tags=["network"])


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
            except Exception:
                pass
    return uid


@router.get("/devices")
def api_device_list(request: Request, keyword: str = "", db: Session = Depends(get_db)):
    devices = network_service.list_devices(db, keyword or None)
    up = sum(1 for d in devices if d["status"] == "ok")
    return JSONResponse({"ok": True, "devices": devices, "device_types": network_service.DEVICE_TYPES,
                         "total": len(devices), "up": up})


@router.get("/devices/{device_id}")
def api_device_get(device_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        detail = network_service.device_detail(db, device_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": True, "device": detail})


@router.post("/devices")
def api_device_create(request: Request, payload: dict, db: Session = Depends(get_db)):
    try:
        d = network_service.create_device(db, payload, created_by=_current_user_id(request))
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "device": network_service._device_dict(d)})


@router.put("/devices/{device_id}")
def api_device_update(device_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    try:
        d = network_service.update_device(db, device_id, payload)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": True, "device": network_service._device_dict(d)})


@router.delete("/devices/{device_id}")
def api_device_delete(device_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        network_service.delete_device(db, device_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": True})


@router.post("/devices/{device_id}/validate")
def api_device_validate(device_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        result = network_service.validate_device(db, device_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": result.get("ok", False), "result": result})


@router.post("/devices/{device_id}/poll")
def api_device_poll(device_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        result = network_service.poll_device(db, device_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": result.get("ok", False), "result": result})


@router.post("/devices/{device_id}/discover")
def api_device_discover(device_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        result = network_service.discover_device(db, device_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": result.get("ok", False), "result": result})


@router.post("/map-links")
def api_map_links(request: Request, payload: dict, db: Session = Depends(get_db)):
    host_ip = str(payload.get("host_ip") or "").strip()
    if not host_ip:
        return JSONResponse({"ok": False, "error": "缺少 host_ip"}, status_code=400)
    result = network_service.map_host_links(db, host_ip)
    return JSONResponse({"ok": True, "result": result})
