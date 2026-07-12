import hashlib

from pathlib import Path

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.template_utils import get_templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import verify_password

router = APIRouter(tags=["auth"])
templates = get_templates()
_limiter = Limiter(key_func=get_remote_address)

_VUE_INDEX = Path(__file__).resolve().parent.parent.parent / "frontend/dist/index.html"


def _serve_vue() -> HTMLResponse:
    content = _VUE_INDEX.read_text(encoding="utf-8")
    return HTMLResponse(content=content)


def hash_password(password: str) -> str:
    """向后兼容的 hash 函数，实际验证用 app.security.verify_password"""
    from app.security import hash_password as _hp
    return _hp(password)


def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_login(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=303)
    return user


class LoginBody(BaseModel):
    username: str
    password: str


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    user_id = request.session.get("user_id")
    if user_id:
        return RedirectResponse("/", status_code=303)
    return _serve_vue()


@router.get("/product", response_class=HTMLResponse)
def product_intro(request: Request):
    return templates.TemplateResponse("product_intro.html", {"request": request})

@router.get("/product/overview", response_class=HTMLResponse)
def product_overview(request: Request):
    return templates.TemplateResponse("product_overview.html", {"request": request})


@router.post("/login")
@_limiter.limit("10/minute")
async def login(request: Request, db: Session = Depends(get_db)):
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        body = await request.json()
        uname = body.get("username", "")
        pwd = body.get("password", "")
        is_json = True
    else:
        form = await request.form()
        uname = form.get("username", "")
        pwd = form.get("password", "")
        is_json = False

    user = db.query(User).filter(User.username == uname).first()
    if not user or not verify_password(pwd, user.password_hash):
        if is_json:
            return JSONResponse({"ok": False, "message": "用户名或密码错误"}, status_code=401)
        return RedirectResponse(url="/login?error=用户名或密码错误", status_code=303)

    request.session["user_id"] = user.id
    request.session["username"] = user.username

    if is_json:
        from app.services.mobile_push_service import issue_login_token
        token = issue_login_token(user.id, user.username)
        return {"ok": True, "message": "登录成功", "token": token, "user": {"id": user.id, "username": user.username, "role": user.role}}
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.post("/refresh")
async def refresh_token(request: Request, db: Session = Depends(get_db)):
    """刷新登录 token（移动端 / API 客户端用）"""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return JSONResponse({"ok": False, "error": "缺少 token"}, status_code=401)
    from app.services.mobile_push_service import verify_login_token, issue_login_token
    payload = verify_login_token(auth[7:])
    if not payload:
        return JSONResponse({"ok": False, "error": "token 已过期，请重新登录"}, status_code=401)
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not user:
        return JSONResponse({"ok": False, "error": "用户不存在"}, status_code=401)
    new_token = issue_login_token(user.id, user.username)
    return {"ok": True, "token": new_token}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    auth = request.headers.get("authorization", "")
    if (not user_id) and auth.startswith("Bearer "):
        from app.services.mobile_push_service import verify_login_token
        payload = verify_login_token(auth[7:])
        if payload:
            user_id = payload.get("user_id")
    if not user_id:
        return JSONResponse({"ok": False, "error": "未登录"}, status_code=401)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return JSONResponse({"ok": False, "error": "用户不存在"}, status_code=401)
    return {"ok": True, "user": {"id": user.id, "username": user.username, "role": user.role}}


