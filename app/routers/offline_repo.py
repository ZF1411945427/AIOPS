"""离线部署路由 - 对标 Pixiu `builder serve`:
- 离线包管理(上传/加载/镜像/删除)
- 私有 Registry 管理(CRUD/测试连接/列镜像)
- 系统包源管理(deb/rpm)
- 健康检查与部署计划离线配置

契约见 CONTRACT.md 第十二章。
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import offline_repo_service
from app.logger import logger

router = APIRouter(prefix="/offline/api", tags=["offline"])


def _get_user_id(request: Request) -> int:
    return request.session.get("user_id", 0)


# ─────────────────────────── 离线包 ───────────────────────────

@router.post("/bundles/upload")
def upload_bundle(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(""),
    bundle_type: str = Form("images"),
    os_type: str = Form(""),
    os_version: str = Form(""),
    version: str = Form(""),
    description: str = Form(""),
    md5: str = Form(""),
    db: Session = Depends(get_db),
):
    try:
        bundle = offline_repo_service.save_bundle(
            db, file, name=name, bundle_type=bundle_type,
            os_type=os_type, os_version=os_version, version=version,
            description=description, md5=md5,
        )
        return {"ok": True, "bundle": bundle}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        logger.exception(f"上传离线包失败: {e}")
        return JSONResponse({"warning": f"上传失败: {e}"}, status_code=200)


@router.get("/bundles")
def list_bundles(search: str = "", status: str = "", page: int = 1, per_page: int = 20,
                 db: Session = Depends(get_db)):
    try:
        return offline_repo_service.list_bundles(db, search=search, status=status, page=page, per_page=per_page)
    except Exception as e:
        return JSONResponse({"warning": str(e), "items": [], "total": 0}, status_code=200)


@router.get("/bundles/{bundle_id}")
def get_bundle(bundle_id: int, db: Session = Depends(get_db)):
    try:
        b = offline_repo_service.get_bundle(db, bundle_id)
        if not b:
            return JSONResponse({"error": "离线包不存在"}, status_code=404)
        return b
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/bundles/{bundle_id}/load")
def load_bundle(bundle_id: int, registry_id: Optional[int] = None, db: Session = Depends(get_db)):
    try:
        result = offline_repo_service.load_bundle(db, bundle_id, registry_id=registry_id)
        return {"ok": True, "bundle": result}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        logger.exception(f"加载离线包失败: {e}")
        return JSONResponse({"warning": f"加载失败: {e}"}, status_code=200)


@router.delete("/bundles/{bundle_id}")
def delete_bundle(bundle_id: int, db: Session = Depends(get_db)):
    try:
        ok = offline_repo_service.delete_bundle(db, bundle_id)
        if not ok:
            return JSONResponse({"error": "离线包不存在"}, status_code=404)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/bundles/{bundle_id}/images")
def list_bundle_images(bundle_id: int, db: Session = Depends(get_db)):
    try:
        return offline_repo_service.list_bundle_images(db, bundle_id)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/bundles/{bundle_id}/packages")
def list_bundle_packages(bundle_id: int, db: Session = Depends(get_db)):
    try:
        return offline_repo_service.list_bundle_packages(db, bundle_id)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


# ─────────────────────────── Registry ───────────────────────────

@router.get("/registries")
def list_registries(db: Session = Depends(get_db)):
    try:
        regs = offline_repo_service.list_registries(db)
        return {"items": regs, "total": len(regs)}
    except Exception as e:
        return JSONResponse({"warning": str(e), "items": []}, status_code=200)


@router.post("/registries")
def create_registry(payload: dict, db: Session = Depends(get_db)):
    try:
        r = offline_repo_service.create_registry(db, payload)
        return {"ok": True, "registry": offline_repo_service._registry_to_dict(r)}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        logger.exception(f"创建 Registry 失败: {e}")
        return JSONResponse({"warning": f"创建失败: {e}"}, status_code=200)


@router.put("/registries/{registry_id}")
def update_registry(registry_id: int, payload: dict, db: Session = Depends(get_db)):
    try:
        r = offline_repo_service.update_registry(db, registry_id, payload)
        if not r:
            return JSONResponse({"error": "Registry 不存在"}, status_code=404)
        return {"ok": True, "registry": offline_repo_service._registry_to_dict(r)}
    except Exception as e:
        logger.exception(f"更新 Registry 失败: {e}")
        return JSONResponse({"warning": f"更新失败: {e}"}, status_code=200)


@router.delete("/registries/{registry_id}")
def delete_registry(registry_id: int, db: Session = Depends(get_db)):
    try:
        ok = offline_repo_service.delete_registry(db, registry_id)
        if not ok:
            return JSONResponse({"error": "Registry 不存在"}, status_code=404)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/registries/{registry_id}")
def get_registry(registry_id: int, db: Session = Depends(get_db)):
    from app.models import OfflineRegistry
    r = db.query(OfflineRegistry).filter(OfflineRegistry.id == registry_id).first()
    if not r:
        return JSONResponse({"error": "Registry 不存在"}, status_code=404)
    return offline_repo_service._registry_to_dict(r, include_password=True)


@router.post("/registries/{registry_id}/test")
def test_registry(registry_id: int, db: Session = Depends(get_db)):
    from app.models import OfflineRegistry
    r = db.query(OfflineRegistry).filter(OfflineRegistry.id == registry_id).first()
    if not r:
        return JSONResponse({"error": "Registry 不存在"}, status_code=404)
    return offline_repo_service.test_registry(r)


@router.get("/registries/{registry_id}/images")
def list_registry_images(registry_id: int, db: Session = Depends(get_db)):
    from app.models import OfflineRegistry
    r = db.query(OfflineRegistry).filter(OfflineRegistry.id == registry_id).first()
    if not r:
        return JSONResponse({"error": "Registry 不存在"}, status_code=404)
    return offline_repo_service.list_registry_images(r)


# ─────────────────────────── 包源 / 健康 ───────────────────────────

@router.get("/sources")
def list_sources(bundle_id: Optional[int] = None, db: Session = Depends(get_db)):
    try:
        return offline_repo_service.list_sources(db, bundle_id=bundle_id)
    except Exception as e:
        return JSONResponse({"warning": str(e), "items": []}, status_code=200)


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    try:
        ok = offline_repo_service.delete_source(db, source_id)
        if not ok:
            return JSONResponse({"error": "包源不存在"}, status_code=404)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/health")
def get_health(db: Session = Depends(get_db)):
    try:
        return offline_repo_service.get_health_status(db)
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/plan/{plan_id}/config")
def get_plan_offline_config(plan_id: int, db: Session = Depends(get_db)):
    """部署计划离线配置（对接 deploy_plans）。"""
    try:
        return offline_repo_service.get_repo_config_for_plan(db, plan_id)
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)