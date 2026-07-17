from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.asset_change_service import get_change_logs
from app.template_utils import get_templates

router = APIRouter(prefix="/asset-changes", tags=["asset_changes"])
templates = get_templates()


@router.get("/status")
def status():
    return {"module": "asset_changes", "status": "ok"}


@router.get("/logs")
def api_change_logs(
    asset_id: int = 0,
    page: int = 1,
    per_page: int = 50,
    db: Session = Depends(get_db)
):
    """查询资产变更日志（支持资产 ID 过滤、分页）."""
    logs = get_change_logs(db, asset_id=asset_id if asset_id else None, limit=per_page)
    return JSONResponse({
        "items": [
            {
                "id": lg.id,
                "asset_id": lg.asset_id,
                "asset_name": lg.asset_name,
                "field": lg.field,
                "old_value": lg.old_value,
                "new_value": lg.new_value,
                "operator": lg.operator,
                "created_at": lg.created_at.strftime("%Y-%m-%d %H:%M:%S") if lg.created_at else None,
            }
            for lg in logs
        ],
        "total": len(logs),
        "page": page,
        "per_page": per_page,
    })
