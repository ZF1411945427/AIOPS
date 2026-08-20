"""告警收敛闭环 API（P2 任务#9）

AIOps 核心闭环：告警聚类 → 关联拓扑 → 根因推荐 → 单一工单。

端点:
- GET  /api/alert-correlation/clusters          列出当前告警聚类（带 30s 缓存）
- GET  /api/alert-correlation/clusters/{id}     单个 cluster 详情（含根因推荐 + 影响路径）
- POST /api/alert-correlation/refresh           强制刷新聚类缓存
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.logger import logger
from app.services import alert_correlation_service

router = APIRouter(prefix="/api/alert-correlation", tags=["alert_correlation"])


@router.get("/clusters")
def list_clusters(
    request: Request,
    window_minutes: int = 5,
    refresh: bool = False,
    db: Session = Depends(get_db),
):
    """列出当前告警聚类（三维度: 服务 / 时间窗 / 拓扑）"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录", "summary": None, "service_clusters": [],
                    "time_clusters": [], "topology_clusters": []}
        data = alert_correlation_service.get_clusters_cached(db, force_refresh=refresh)
        # window_minutes 仅在强制刷新时生效
        if refresh and window_minutes != 5:
            data = alert_correlation_service.cluster_alerts(db, window_minutes=window_minutes)
        return data
    except Exception as e:
        logger.warning(f"list_clusters 异常: {e}")
        return {
            "warning": str(e), "summary": None,
            "service_clusters": [], "time_clusters": [], "topology_clusters": [],
        }


@router.get("/clusters/{cluster_id}")
def get_cluster(cluster_id: str, request: Request, db: Session = Depends(get_db)):
    """获取单个 cluster 详情：含根因推荐 + 拓扑影响路径"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录", "cluster": None}
        return alert_correlation_service.cluster_detail(db, cluster_id)
    except Exception as e:
        logger.warning(f"get_cluster 异常: {e}")
        return {"warning": str(e), "cluster": None}


@router.post("/refresh")
def refresh_clusters(request: Request, window_minutes: int = 5, db: Session = Depends(get_db)):
    """强制刷新聚类缓存"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录"}
        data = alert_correlation_service.cluster_alerts(db, window_minutes=window_minutes)
        return {"ok": True, "summary": data.get("summary")}
    except Exception as e:
        logger.warning(f"refresh_clusters 异常: {e}")
        return {"ok": False, "message": str(e)}


@router.get("/persisted")
def list_persisted(
    request: Request,
    limit: int = 50,
    cluster_type: str = "",
    db: Session = Depends(get_db),
):
    """查询已落库的告警聚类（含自动生成的故障单关联）"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录", "items": []}
        items = alert_correlation_service.list_persisted_clusters(
            db, limit=limit, cluster_type=cluster_type or None
        )
        return {"items": items, "count": len(items)}
    except Exception as e:
        logger.warning(f"list_persisted 异常: {e}")
        return {"warning": str(e), "items": []}


@router.post("/persist")
def persist_now(request: Request, auto_incident: bool = True, db: Session = Depends(get_db)):
    """手动触发一次聚类落库 + 自动生成故障单"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录"}
        result = alert_correlation_service.persist_clusters(db, auto_incident=auto_incident)
        return {"ok": True, **result}
    except Exception as e:
        logger.warning(f"persist_now 异常: {e}")
        return {"ok": False, "message": str(e)}
