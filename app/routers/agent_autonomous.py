"""自主 AI Agent 闭环 API — 巡检历史、手动触发、状态查询。"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.agent_autonomous import run_autonomous_cycle, get_cycle_history

router = APIRouter(prefix="/agent/autonomous", tags=["agent-autonomous"])


@router.get("/history")
def list_cycle_history(request: Request, db: Session = Depends(get_db), limit: int = Query(20, le=100)):
    """获取自主巡检闭环历史。"""
    return {"cycles": get_cycle_history(db, limit=limit)}


@router.post("/trigger")
def trigger_cycle(request: Request, db: Session = Depends(get_db)):
    """手动触发一轮自主巡检。"""
    import threading
    def _run():
        run_autonomous_cycle()
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"ok": True, "message": "自主巡检已触发，请稍后查看结果"}