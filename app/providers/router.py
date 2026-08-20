from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.database import get_db
from app.providers.service import ProviderService
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("/catalog")
def list_provider_catalog():
    return JSONResponse({
        "providers": ProviderService.get_provider_catalog(),
        "categories": ProviderService.get_providers_by_category(),
    })


@router.get("/installed")
def list_installed_providers(db: Session = Depends(get_db)):
    return JSONResponse({"installed": ProviderService.list_installed(db)})


@router.get("/installed/{source_id}")
def get_installed_provider(source_id: int, db: Session = Depends(get_db)):
    result = ProviderService.get_installed(db, source_id)
    if not result:
        return JSONResponse({"error": "Provider 不存在"}, status_code=404)
    return JSONResponse(result)


@router.post("/install")
async def install_provider(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    if not body.get("type") or not body.get("name"):
        return JSONResponse({"error": "type 和 name 为必填项"}, status_code=400)
    try:
        result = ProviderService.install(db, body)
        return JSONResponse({"ok": True, "provider": result})
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.put("/installed/{source_id}")
async def update_provider(source_id: int, request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    result = ProviderService.update_installed(db, source_id, body)
    if not result:
        return JSONResponse({"error": "Provider 不存在"}, status_code=404)
    return JSONResponse({"ok": True, "provider": result})


@router.post("/installed/{source_id}/uninstall")
def uninstall_provider(source_id: int, db: Session = Depends(get_db)):
    if ProviderService.uninstall(db, source_id):
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "Provider 不存在"}, status_code=404)


@router.post("/installed/{source_id}/test")
def test_provider(source_id: int, db: Session = Depends(get_db)):
    ok, msg = ProviderService.test_connection(db, source_id)
    return JSONResponse({"ok": ok, "message": msg})


@router.post("/installed/{source_id}/scrape")
def scrape_provider(source_id: int, db: Session = Depends(get_db)):
    ok, msg = ProviderService.scrape(db, source_id)
    return JSONResponse({"ok": ok, "message": msg})


@router.post("/installed/{source_id}/toggle")
def toggle_provider(source_id: int, db: Session = Depends(get_db)):
    result = ProviderService.get_installed(db, source_id)
    if not result:
        return JSONResponse({"error": "Provider 不存在"}, status_code=404)
    ProviderService.update_installed(db, source_id, {"enabled": not result["enabled"]})
    return JSONResponse({"ok": True})