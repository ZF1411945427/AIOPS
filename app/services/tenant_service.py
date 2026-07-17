"""
租户服务
"""
import json
from datetime import datetime
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models import Tenant
from app.services.config_service import get_config

TENANT_MODE_KEY = "tenant_mode"
DEFAULT_TENANT_ID = 1

def is_tenant_mode_enabled(db: Session) -> bool:
    return get_config(db, TENANT_MODE_KEY, "false") == "true"

def get_default_tenant_id() -> int:
    return DEFAULT_TENANT_ID

def get_or_create_default_tenant(db: Session) -> Tenant:
    t = db.query(Tenant).filter(Tenant.code == "default").first()
    if not t:
        t = Tenant(name="默认租户", code="default", status="active", quota_assets=10000, quota_users=1000)
        db.add(t)
        db.commit()
        db.refresh(t)
    return t

def ensure_tenant_exists(db: Session, tenant_id: int) -> bool:
    t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    return t is not None

def list_tenants(db: Session) -> List[dict]:
    rows = db.query(Tenant).order_by(Tenant.id).all()
    return [_t_to_dict(r) for r in rows]

def get_tenant(db: Session, tenant_id: int) -> Optional[dict]:
    t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    return _t_to_dict(t) if t else None

def create_tenant(db: Session, data: dict) -> dict:
    t = Tenant(
        name=data["name"],
        code=data["code"],
        status=data.get("status", "active"),
        quota_assets=data.get("quota_assets", 1000),
        quota_users=data.get("quota_users", 50),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _t_to_dict(t)

def update_tenant(db: Session, tenant_id: int, data: dict) -> Optional[dict]:
    t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not t:
        return None
    for key in ["name", "status", "quota_assets", "quota_users"]:
        if key in data:
            setattr(t, key, data[key])
    t.updated_at = datetime.now()
    db.commit()
    db.refresh(t)
    return _t_to_dict(t)

def delete_tenant(db: Session, tenant_id: int) -> bool:
    if tenant_id == DEFAULT_TENANT_ID:
        return False
    t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not t:
        return False
    db.delete(t)
    db.commit()
    return True

def _t_to_dict(t: Tenant) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "code": t.code,
        "status": t.status,
        "quota_assets": t.quota_assets,
        "quota_users": t.quota_users,
        "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else None,
        "updated_at": t.updated_at.strftime("%Y-%m-%d %H:%M:%S") if t.updated_at else None,
    }
