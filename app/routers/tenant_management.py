"""
租户管理 API
"""
from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import tenant_service

router = APIRouter(prefix="/tenant/api", tags=["TenantManagement"])

@router.get("/tenants")
def list_tenants(db: Session = Depends(get_db)):
    return {"items": tenant_service.list_tenants(db)}

@router.post("/tenants")
def create_tenant(payload: dict = Body(...), db: Session = Depends(get_db)):
    data = {k: v for k, v in payload.items() if k not in ("id", "created_at")}
    t = tenant_service.create_tenant(db, data)
    return {"ok": True, "tenant": t}

@router.get("/tenants/{tenant_id}")
def get_tenant(tenant_id: int, db: Session = Depends(get_db)):
    t = tenant_service.get_tenant(db, tenant_id)
    if not t:
        return {"error": "Not found"}, 404
    return t

@router.put("/tenants/{tenant_id}")
def update_tenant(tenant_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    data = {k: v for k, v in payload.items() if k not in ("id", "created_at")}
    t = tenant_service.update_tenant(db, tenant_id, data)
    if not t:
        return {"error": "Not found"}, 404
    return {"ok": True}

@router.delete("/tenants/{tenant_id}")
def delete_tenant(tenant_id: int, db: Session = Depends(get_db)):
    ok = tenant_service.delete_tenant(db, tenant_id)
    return {"ok": ok}
