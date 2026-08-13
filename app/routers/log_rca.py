from datetime import datetime
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import rca_algos_service

router = APIRouter(prefix="/log-rca", tags=["log-rca"])


@router.get("/status")
def status():
    return {"module": "log_rca", "status": "ok", "version": "real"}


@router.get("/analyze/{asset_id}")
def analyze(asset_id: int, hours: float = 24, keyword: str = "", db: Session = Depends(get_db)):
    result = rca_algos_service.run_log_rca(db, asset_id, hours=hours, keyword=keyword)
    return JSONResponse({"ok": result.get("ok", False), "result": result})
