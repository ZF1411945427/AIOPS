import hashlib

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.template_utils import get_templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

router = APIRouter(prefix="/users", tags=["users"])
templates = get_templates()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def require_admin(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if not user or user.role != "admin":
        return None
    return user


@router.get("", response_class=HTMLResponse)
def user_list(request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    if not admin:
        return RedirectResponse("/", status_code=303)
    users = db.query(User).order_by(User.id.asc()).all()
    return templates.TemplateResponse("users.html", {"request": request, "users": users})


@router.post("/create")
def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("operator"),
    db: Session = Depends(get_db),
):
    admin = require_admin(request, db)
    if not admin:
        return RedirectResponse("/", status_code=303)
    existing = db.query(User).filter(User.username == username).first()
    if not existing:
        user = User(username=username, password_hash=hash_password(password), role=role)
        db.add(user)
        db.commit()
    return RedirectResponse("/users", status_code=303)


@router.post("/{user_id}/delete")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    if not admin or user_id == admin.id:
        return RedirectResponse("/users", status_code=303)
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    return RedirectResponse("/users", status_code=303)


