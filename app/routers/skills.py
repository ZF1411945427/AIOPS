"""技能库 API（F1 SKILL.md 技能规范 + 注册表）。契约见 CONTRACT.md 第十九章。"""
from datetime import datetime

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from app.database import get_db
from app.services import skill_registry
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/skills", tags=["skills"])

_RISK_LEVELS = ["read_only", "interactive", "danger"]
_MAX_UPLOAD = 2 * 1024 * 1024  # 2MB


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
            except Exception as _exc:
                logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)
    return user_id


@router.get("")
def api_skill_list(request: Request, keyword: str = "", db: Session = Depends(get_db)):
    return JSONResponse({
        "ok": True,
        "skills": skill_registry.list_skills(db, keyword or None),
        "risk_levels": _RISK_LEVELS,
        "total": len(skill_registry.list_skills(db)),
    })


@router.get("/executions")
def api_skill_executions(request: Request, limit: int = 100, db: Session = Depends(get_db)):
    return JSONResponse({
        "ok": True,
        "executions": skill_registry.list_executions(db, min(max(limit, 1), 500)),
    })


@router.get("/{skill_id}")
def api_skill_get(skill_id: int, db: Session = Depends(get_db)):
    skill = skill_registry.get_skill(db, skill_id)
    if not skill:
        return JSONResponse({"ok": False, "error": "技能不存在"}, status_code=404)
    data = skill_registry._to_dict(skill)
    data["content"] = skill.content
    return JSONResponse({"ok": True, "skill": data})


@router.post("")
def api_skill_create(request: Request, payload: dict, db: Session = Depends(get_db)):
    try:
        skill = skill_registry.create_skill(db, payload, created_by=_current_user_id(request))
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "skill": skill_registry._to_dict(skill)})


@router.put("/{skill_id}")
def api_skill_update(skill_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    try:
        skill = skill_registry.update_skill(db, skill_id, payload)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": True, "skill": skill_registry._to_dict(skill)})


@router.delete("/{skill_id}")
def api_skill_delete(skill_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        result = skill_registry.delete_skill(db, skill_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": True, **result})


@router.post("/{skill_id}/run")
def api_skill_run(skill_id: int, request: Request, payload: dict = None, db: Session = Depends(get_db)):
    skill = skill_registry.get_skill(db, skill_id)
    if not skill:
        return JSONResponse({"ok": False, "error": "技能不存在"}, status_code=404)
    if not skill.enabled:
        return JSONResponse({"ok": False, "error": "技能已禁用"}, status_code=400)
    inputs = payload or {}
    start = datetime.now()
    status, out = "success", f"技能指令已加载({len(skill.content)} 字符), 按 instructions 执行"
    duration = int((datetime.now() - start).total_seconds() * 1000)
    skill_registry.record_execution(db, skill.id, skill.name, "manual", status,
                                    json_dumps(inputs), out, duration,
                                    executed_by=_current_user_id(request))
    return JSONResponse({"ok": True, "status": status, "output_summary": out,
                         "instructions": skill.content})


@router.get("/{skill_id}/export")
def api_skill_export(skill_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        data = skill_registry.export_package(db, skill_id)
        skill = skill_registry.get_skill(db, skill_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return Response(content=data,
                    media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{skill.name}-{skill.version}.zip"'})


@router.post("/import")
async def api_skill_import(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    data_bytes = await file.read()
    if not data_bytes:
        return JSONResponse({"ok": False, "error": "空文件"}, status_code=400)
    if len(data_bytes) > _MAX_UPLOAD:
        return JSONResponse({"ok": False, "error": "技能包超过 2MB 限制"}, status_code=400)
    try:
        skill = skill_registry.import_package(db, data_bytes, created_by=_current_user_id(request),
                                              source="upload")
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "skill": skill_registry._to_dict(skill)})


def json_dumps(obj) -> str:
    import json
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)[:500]
    except Exception:
        return str(obj)[:500]


import logging
logger = logging.getLogger(__name__)
