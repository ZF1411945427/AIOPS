from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import rca_algos_service

router = APIRouter(prefix="/idice", tags=["idice"])


@router.get("/status")
def status():
    return {"module": "idice", "status": "ok", "version": "real"}


@router.get("/attribute/{asset_id}")
def attribute(asset_id: int, target_metric: str = "", hours: float = 24, db: Session = Depends(get_db)):
    result = rca_algos_service.run_idice(db, asset_id, target_metric=target_metric, hours=hours)
    return JSONResponse({"ok": result.get("ok", False), "result": result})
