from fastapi import APIRouter, Depends, Request, Body
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import config_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/api/list")
def api_settings_list(db: Session = Depends(get_db)):
    return {"configs": config_service.get_all_configs(db)}


@router.post("/api/update")
def api_settings_update(payload: dict = Body(...), db: Session = Depends(get_db)):
    updates = {k: str(v) for k, v in payload.items() if k != "db"}
    config_service.update_configs(db, updates)
    return {"status": "ok"}
