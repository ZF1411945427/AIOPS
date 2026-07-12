from fastapi import APIRouter, Depends, Request, Body
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models import User
from app.security import hash_password, verify_password

router = APIRouter(prefix="/users", tags=["users"])
_limiter = Limiter(key_func=get_remote_address)


def require_admin(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if not user or user.role != "admin":
        return None
    return user


@router.get("/api/list")
def api_user_list(request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    if not admin:
        return {"error": "forbidden", "users": []}
    users = db.query(User).order_by(User.id.asc()).all()
    return {
        "users": [
            {
                "id": u.id, "username": u.username, "role": u.role,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
        "current_user_id": admin.id,
        "count": len(users),
    }


@router.post("/api/create")
@_limiter.limit("5/minute")
def api_user_create(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    if not admin:
        return {"status": "error", "message": "无权限"}
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    role = payload.get("role", "operator")
    if not username or not password:
        return {"status": "error", "message": "用户名和密码不能为空"}
    if role not in ("admin", "operator", "viewer"):
        role = "operator"
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return {"status": "error", "message": "用户名已存在"}
    user = User(username=username, password_hash=hash_password(password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"status": "ok", "id": user.id}


@router.delete("/api/{user_id}/delete")
def api_user_delete(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    if not admin:
        return {"status": "error", "message": "无权限"}
    if user_id == admin.id:
        return {"status": "error", "message": "不能删除当前登录用户"}
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    return {"status": "ok"}


@router.post("/api/{user_id}/reset-password")
@_limiter.limit("5/minute")
def api_reset_password(user_id: int, payload: dict = Body(...), request: Request = None, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    if not admin:
        return {"status": "error", "message": "无权限"}
    new_password = payload.get("new_password", "")
    if not new_password or len(new_password) < 4:
        return {"status": "error", "message": "新密码不能为空且至少4位"}
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"status": "error", "message": "用户不存在"}
    user.password_hash = hash_password(new_password)
    db.commit()
    return {"status": "ok"}


@router.post("/api/change-password")
@_limiter.limit("5/minute")
def api_change_password(payload: dict = Body(...), request: Request = None, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return {"status": "error", "message": "未登录"}
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"status": "error", "message": "用户不存在"}
    old_password = payload.get("old_password", "")
    new_password = payload.get("new_password", "")
    if not old_password or not new_password:
        return {"status": "error", "message": "旧密码和新密码不能为空"}
    if not verify_password(old_password, user.password_hash):
        return {"status": "error", "message": "旧密码错误"}
    if len(new_password) < 4:
        return {"status": "error", "message": "新密码至少4位"}
    if verify_password(new_password, user.password_hash):
        return {"status": "error", "message": "新密码不能与旧密码相同"}
    user.password_hash = hash_password(new_password)
    db.commit()
    return {"status": "ok"}
