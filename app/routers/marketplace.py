"""技能市场 Marketplace API（F2 打包安装/私服分发）。契约见 CONTRACT.md 第十九章。"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.database import get_db
from app.models import SystemConfig
from app.services import skill_registry, skill_remote
from sqlalchemy.orm import Session

import logging
logger = logging.getLogger(__name__)

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
            except Exception as _exc:
                logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)
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


# ─── 远程技能源(对接 skills.sh 生态的 GitHub 仓库) ─────────────────
# 契约: CONTRACT.md 19.x —— Skill.source 新增 remote。

@router.get("/remote/presets")
def api_remote_presets(request: Request):
    """预设的社区技能仓库清单。"""
    return JSONResponse({"ok": True, "presets": skill_remote.list_presets()})


@router.get("/remote/repos/{owner}/{repo}/skills")
def api_remote_repo_skills(owner: str, repo: str, request: Request,
                           db: Session = Depends(get_db), branch: str = ""):
    """列出指定 GitHub 仓库 skills/ 目录下的技能（基于 skills.sh 标准的仓库）。"""
    branch = branch or skill_remote.DEFAULT_BRANCH
    try:
        skills = skill_remote.list_repo_skills(owner, repo, branch, db=db)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    llm_evaluated = any(s.get("description_zh") or s.get("reason") for s in skills)
    return JSONResponse({"ok": True, "owner": owner, "repo": repo, "branch": branch,
                         "skills": skills, "llm_evaluated": bool(llm_evaluated)})


@router.get("/remote/repos/{owner}/{repo}/skills/{skill:path}")
def api_remote_repo_skill_preview(owner: str, repo: str, skill: str,
                                  request: Request, db: Session = Depends(get_db), branch: str = ""):
    """预览单个远程技能: 元数据 + SKILL.md 正文。"""
    branch = branch or skill_remote.DEFAULT_BRANCH
    try:
        data = skill_remote.preview_remote_skill(owner, repo, skill, branch, db=db)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:
        logger.exception("preview_remote_skill failed")
        return JSONResponse({"ok": False, "error": f"预览失败: {type(e).__name__}"}, status_code=500)
    return JSONResponse({"ok": True, **data})


@router.post("/remote/install")
def api_remote_install(request: Request, payload: dict, db: Session = Depends(get_db)):
    """从远程仓库安装单个技能到技能库(source=remote)。重名报错。"""
    owner = str(payload.get("owner") or "")
    repo = str(payload.get("repo") or "")
    skill = str(payload.get("skill") or "")
    branch = str(payload.get("branch") or "") or skill_remote.DEFAULT_BRANCH
    if not (owner and repo and skill):
        return JSONResponse({"ok": False, "error": "缺少 owner/repo/skill 参数"}, status_code=400)
    try:
        s = skill_remote.install_remote_skill(db, owner, repo, skill,
                                              created_by=_current_user_id(request), branch=branch)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "skill": skill_registry._to_dict(s),
                         "message": f"已从远程安装 {s.name} v{s.version}"})


# ─── 远程技能源 GitHub Token 管理(系统层可配置, 掩码存储) ────────────
# 契约: SystemConfig key `github_api_token`; 列表掩码 *** + has_value, 空值=不更新, clear=true 清除。

@router.get("/remote/token")
def api_remote_token_get(request: Request, db: Session = Depends(get_db)):
    """查询 GitHub Token 是否已配置(不回显明文)。"""
    token = skill_remote.resolve_github_token(db)
    if token:
        src = "system" if db.query(SystemConfig).filter(
            SystemConfig.key == "github_api_token").first() else (
            "env" if token else "none")
        return JSONResponse({"ok": True, "has_value": True, "value": "***",
                             "source": "system" if db.query(SystemConfig).filter(
                                 SystemConfig.key == "github_api_token").first() else "env"})
    return JSONResponse({"ok": True, "has_value": False, "value": "", "source": "none"})


@router.post("/remote/token")
def api_remote_token_set(payload: dict, request: Request, db: Session = Depends(get_db)):
    """设置 GitHub Token。空字符串=不更新; clear=true 清除。"""
    from app.services.config_service import update_config
    if payload.get("clear"):
        row = db.query(SystemConfig).filter(SystemConfig.key == "github_api_token").first()
        if row:
            db.delete(row)
            db.commit()
        return JSONResponse({"ok": True, "message": "已清除 GitHub Token"})
    new_token = str(payload.get("token") or "").strip()
    if new_token:
        update_config(db, "github_api_token", new_token)
        return JSONResponse({"ok": True, "message": "GitHub Token 已保存"})
    return JSONResponse({"ok": True, "message": "未修改(Token 为空=保留原值)"})
