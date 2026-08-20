"""Granger 因果检验 API。

真实实现(P3-2 补全): 基于 statsmodels.grangercausalitytests 双向检验
指标 A/B 之间是否互为 Granger 因果。原桩(/status)保留用于连通性探活。
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.rca_algos_service import run_granger

router = APIRouter(prefix="/granger", tags=["granger"])


@router.get("/status")
def status():
    """连通性探活（原桩保留）。"""
    return {"module": "granger", "status": "ok", "implemented": True}


@router.get("/analyze")
def analyze(
    db: Session = Depends(get_db),
    asset_id: int = Query(..., description="资产 ID"),
    metric_a: str = Query(..., description="指标 A（原因/响应候选）"),
    metric_b: str = Query(..., description="指标 B（原因/响应候选）"),
    hours: float = Query(24, description="分析窗口（小时）"),
    maxlag: int = Query(3, ge=1, le=10, description="最大滞后阶数"),
):
    """双向 Granger 因果检验: 判断 A 的历史是否显著预测 B, 以及反向。"""
    try:
        result = run_granger(db, asset_id=asset_id, metric_a=metric_a,
                             metric_b=metric_b, hours=hours, maxlag=maxlag)
        if not result.get("ok"):
            return JSONResponse({"ok": False, **result}, status_code=200)
        return {"ok": True, **result}
    except Exception as e:
        from app.logger import logger
        logger.error(f"granger analyze failed: {e}")
        return JSONResponse({"ok": False, "error": f"分析失败: {e}"}, status_code=200)
