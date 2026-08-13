"""技能市场 Marketplace API（F2 打包安装/私服分发）。契约见 CONTRACT.md 第十九章。"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.database import get_db
from app.services import skill_registry
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


def _current_user_id(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            try:
                from app.services.mobile_push_service import verify_login_token
                payload = verify_login_token(auth[7:])
                if payload:
                    user_id = payload.get("user_id")
            except Exception:
                pass
    return user_id


@router.get("/packages")
def api_marketplace_list(request: Request):
    return JSONResponse({"ok": True, "packages": skill_registry.scan_marketplace_packages()})


@router.post("/publish")
def api_marketplace_publish(request: Request, payload: dict, db: Session = Depends(get_db)):
    skill_id = payload.get("skill_id")
    try:
        pkg_name = skill_registry.publish_to_marketplace(db, int(skill_id))
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": True, "package": pkg_name,
                         "message": f"已发布到市场: {pkg_name}"})


@router.post("/install")
def api_marketplace_install(request: Request, payload: dict, db: Session = Depends(get_db)):
    package = str(payload.get("package") or "")
    if not package:
        return JSONResponse({"ok": False, "error": "缺少 package 参数"}, status_code=400)
    try:
        skill = skill_registry.install_from_marketplace(db, package,
                                                        created_by=_current_user_id(request))
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "skill": skill_registry._to_dict(skill),
                         "message": f"已从市场安装 {skill.name} v{skill.version}"})


@router.delete("/packages/{package}")
def api_marketplace_delete(package: str, request: Request):
    skill_registry.delete_marketplace_package(package)
    return JSONResponse({"ok": True, "message": f"已删除市场包 {package}"})
