import json
import os

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse

from app.services.license_service import (
    get_status,
    save_license,
    get_machine_fingerprint,
    check_license,
    parse_license,
    LICENSE_FILE,
    STATE_FILE,
    invalidate_cache,
)

router = APIRouter(prefix="/license", tags=["license"])


@router.get("/api/status")
def license_status():
    return JSONResponse(get_status())


@router.get("/api/fingerprint")
def license_fingerprint():
    fp = get_machine_fingerprint()
    return JSONResponse({"fingerprint": fp, "masked": fp[:8] + "..."})


@router.post("/api/upload")
async def license_upload(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        text = raw.decode("utf-8")
    except Exception as e:
        return JSONResponse(status_code=400, content={"ok": False, "message": f"文件读取失败: {e}", "info": None})
    parsed = parse_license(text)
    if not parsed["valid"]:
        return JSONResponse(status_code=400, content={"ok": False, "message": parsed["reason"], "info": None})
    result = save_license(text)
    invalidate_cache()
    status_code = 200 if result.get("ok") else 400
    return JSONResponse(status_code=status_code, content=result)


@router.get("/api/download-state")
def license_download_state():
    target = STATE_FILE
    if not os.path.exists(target):
        return JSONResponse(status_code=404, content={"detail": "授权状态文件不存在"})
    return FileResponse(target, filename="license_state.json", media_type="application/json")


@router.get("/api/download-license")
def license_download_license():
    if not os.path.exists(LICENSE_FILE):
        return JSONResponse(status_code=404, content={"detail": "授权文件不存在"})
    return FileResponse(LICENSE_FILE, filename="license.lic", media_type="application/octet-stream")


@router.post("/api/refresh")
def license_refresh():
    invalidate_cache()
    return JSONResponse(get_status())
