from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.pcadr_service import run_pcadr

router = APIRouter(prefix="/pcadr", tags=["pcadr"])


@router.get("/analyze")
def pcadr_analyze(
    db: Session = Depends(get_db),
    incident_id: int = Query(None, description="事件 ID"),
    asset_id: int = Query(None, description="资产 ID"),
    hours: int = Query(6, description="分析窗口（小时）"),
):
    """PCA 根因分析：基于主成分分析识别指标异常贡献"""
    try:
        result = run_pcadr(db, incident_id=incident_id, asset_id=asset_id, hours=hours)
        return result
    except Exception as e:
        from app.logger import logger
        logger.error(f"pcadr analyze failed: {e}")
        return JSONResponse({"message": "分析失败"}, status_code=200)
