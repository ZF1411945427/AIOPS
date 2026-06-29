from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.asset_change_service import get_change_logs
from app.template_utils import get_templates

router = APIRouter(prefix="/asset-changes", tags=["asset_changes"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def list_changes(request: Request, asset_id: int = 0, db: Session = Depends(get_db)):
    logs = get_change_logs(db, asset_id if asset_id else None)
    return templates.TemplateResponse("asset_changes.html", {"request": request, "logs": logs, "asset_id": asset_id})
