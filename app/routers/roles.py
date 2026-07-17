import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Role, RoleMenu
from pydantic import BaseModel

router = APIRouter(prefix="/api/roles", tags=["roles"])


class RoleCreate(BaseModel):
    name: str
    description: str = ""
    sort_order: int = 0


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class MenuAssign(BaseModel):
    menu_keys: list[str]


@router.get("")
def list_roles(db: Session = Depends(get_db)):
    roles = db.query(Role).order_by(Role.sort_order, Role.id).all()
    return {
        "ok": True,
        "roles": [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "is_system": r.is_system,
                "is_active": r.is_active,
                "sort_order": r.sort_order,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in roles
        ],
    }


@router.post("")
def create_role(body: RoleCreate, db: Session = Depends(get_db)):
    existing = db.query(Role).filter(Role.name == body.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="角色名称已存在")
    role = Role(
        name=body.name,
        description=body.description,
        sort_order=body.sort_order,
        is_system=False,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return {"ok": True, "role": {"id": role.id, "name": role.name}}


@router.put("/{role_id}")
def update_role(role_id: int, body: RoleUpdate, db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    if body.name is not None:
        role.name = body.name
    if body.description is not None:
        role.description = body.description
    if body.is_active is not None:
        role.is_active = body.is_active
    if body.sort_order is not None:
        role.sort_order = body.sort_order
    db.commit()
    return {"ok": True}


@router.delete("/{role_id}")
def delete_role(role_id: int, db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    if role.is_system:
        raise HTTPException(status_code=400, detail="系统内置角色不可删除")
    db.query(RoleMenu).filter(RoleMenu.role_id == role_id).delete()
    db.delete(role)
    db.commit()
    return {"ok": True}


@router.get("/{role_id}/menus")
def get_role_menus(role_id: int, db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    menu_keys = [rm.menu_key for rm in db.query(RoleMenu).filter(RoleMenu.role_id == role_id).all()]
    return {"ok": True, "menu_keys": menu_keys}


@router.put("/{role_id}/menus")
def set_role_menus(role_id: int, body: MenuAssign, db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    db.query(RoleMenu).filter(RoleMenu.role_id == role_id).delete()
    for key in body.menu_keys:
        db.add(RoleMenu(role_id=role_id, menu_key=key))
    db.commit()
    return {"ok": True, "menu_keys": body.menu_keys}


@router.get("/{role_id}/users")
def get_role_users(role_id: int, db: Session = Depends(get_db)):
    from app.models import User
    users = db.query(User).filter(User.role_id == role_id).all()
    return {
        "ok": True,
        "users": [
            {"id": u.id, "username": u.username, "role": u.role, "role_id": u.role_id}
            for u in users
        ],
    }
