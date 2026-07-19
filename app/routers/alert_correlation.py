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
