from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.rca_service import analyze_pagerank

router = APIRouter(prefix="/pagerank-rca", tags=["pagerank_rca"])


@router.get("/analyze")
def pagerank_analyze(
    db: Session = Depends(get_db),
    incident_id: int = Query(None, description="事件 ID"),
    damping: float = Query(0.85, description="阻尼系数"),
    max_iter: int = Query(100, description="最大迭代次数"),
):
    """PageRank 根因分析：基于资产依赖图计算各节点的 PageRank 值"""
    try:
        result = analyze_pagerank(db, incident_id=incident_id, damping=damping, max_iter=max_iter)
        return result
    except Exception as e:
        from app.logger import logger
        logger.error(f"pagerank-rca analyze failed: {e}")
        return JSONResponse({"message": "分析失败"}, status_code=200)
