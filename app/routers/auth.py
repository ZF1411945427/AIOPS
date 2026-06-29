import hashlib

from pathlib import Path

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.template_utils import get_templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

router = APIRouter(tags=["auth"])
templates = get_templates()

_VUE_INDEX = Path(__file__).resolve().parent.parent.parent / "frontend/dist/index.html"


def _serve_vue() -> HTMLResponse:
    content = _VUE_INDEX.read_text(encoding="utf-8")
    content = content.replace('/assets/', '/vue-assets/assets/')
    return HTMLResponse(content=content)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


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


@router.post("/login")
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
    if not user or user.password_hash != hash_password(pwd):
        if is_json:
            return JSONResponse({"ok": False, "message": "用户名或密码错误"}, status_code=401)
        return templates.TemplateResponse("login.html", {"request": request, "error": "用户名或密码错误"})

    request.session["user_id"] = user.id

    if is_json:
        return {"ok": True, "message": "登录成功"}
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


