from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.dtw_service import find_similar_metrics

router = APIRouter(prefix="/dtw", tags=["dtw"])


@router.get("/similar")
def similar_metrics(
    db: Session = Depends(get_db),
    metric_name: str = Query(..., description="指标名称"),
    asset_id: int = Query(None, description="资产 ID"),
    hours: int = Query(6, description="分析窗口（小时）"),
    top_k: int = Query(10, description="返回数量"),
):
    """DTW 相似指标搜索：基于动态时间规距找相似指标序列"""
    try:
        result = find_similar_metrics(db, metric_name=metric_name, asset_id=asset_id, hours=hours, top_k=top_k)
        return {"results": result, "count": len(result)}
    except Exception as e:
        from app.logger import logger
        logger.error(f"dtw similar failed: {e}")
        return JSONResponse({"message": "查询失败"}, status_code=200)
