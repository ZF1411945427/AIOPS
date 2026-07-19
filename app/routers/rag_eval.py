"""RAG 检索质量评估 API（P2 任务#10）

端点:
- GET  /api/rag/eval          跑评估出指标（recall@k / MRR / nDCG / 平均延迟）
- POST /api/rag/eval/run      强制重新跑评估
- GET  /api/rag/eval/dataset  查看当前评估数据集
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.logger import logger
from app.services import rag_eval_service

router = APIRouter(prefix="/api/rag/eval", tags=["rag_eval"])


@router.get("")
def get_eval(
    request: Request,
    top_k: int = 5,
    limit: int = 50,
    refresh: bool = False,
    db: Session = Depends(get_db),
):
    """RAG 检索质量评估：recall@k / MRR / nDCG@k / 平均延迟"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录", "summary": None, "samples": []}
        return rag_eval_service.get_eval_cached(db, top_k=top_k, limit=limit, force_refresh=refresh)
    except Exception as e:
        logger.warning(f"get_eval 异常: {e}")
        return {"warning": str(e), "summary": None, "samples": []}


@router.post("/run")
def run_eval(
    request: Request,
    top_k: int = 5,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """强制重新跑评估（不读缓存）"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录"}
        data = rag_eval_service.run_eval(db, top_k=top_k, limit=limit)
        return {"ok": True, "summary": data.get("summary"), "sample_count": len(data.get("samples", []))}
    except Exception as e:
        logger.warning(f"run_eval 异常: {e}")
        return {"ok": False, "message": str(e)}


@router.get("/dataset")
def get_dataset(request: Request, limit: int = 50, db: Session = Depends(get_db)):
    """查看当前评估数据集（不跑检索）"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录", "total": 0, "samples": []}
        return rag_eval_service.get_dataset(db, limit=limit)
    except Exception as e:
        logger.warning(f"get_dataset 异常: {e}")
        return {"warning": str(e), "total": 0, "samples": []}
