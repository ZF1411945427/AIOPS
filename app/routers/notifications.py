from fastapi import APIRouter, Depends, Request, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from datetime import datetime, timedelta

from app.database import get_db
from app.services import notification_service
from app.models import Alert, Asset, Incident, PendingAction

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/api/recent")
def recent_notifications(db: Session = Depends(get_db)):
    """实时聚合系统通知，供顶栏铃铛拉取.

    数据源全部为真实数据库查询：
    - 未处理告警（status=triggered/firing，最近24h，按严重程度+时间排序取前5）
    - 未解决事件（incidents.status != resolved/closed，最近3条）
    - 离线资产（assets.status != online，按最近检查时间排序取前3）
    - 待确认AI动作（pending_actions.status=pending，前3条）
    返回 {notifications: [...], count: N}, count=未读总数（=告警+事件+待确认）.
    """
    now = datetime.now()
    day_ago = now - timedelta(hours=24)
    notifications = []

    alerts = (
        db.query(Alert)
        .filter(Alert.status.in_(["triggered", "firing"]))
        .filter(Alert.created_at >= day_ago)
        .order_by(
            case((Alert.severity == "critical", 0), else_=1),
            Alert.created_at.desc())
        .limit(5)
        .all()
    )
    for a in alerts:
        icon = "🚨" if a.severity == "critical" else "⚠️"
        msg = (a.message or "")[:80]
        notifications.append({
            "icon": icon,
            "title": f"告警: {msg}",
            "time": _relative_time(a.created_at, now),
            "route": "alerts",
            "severity": a.severity,
        })

    incidents = (
        db.query(Incident)
        .filter(~Incident.status.in_(["resolved", "closed"]))
        .order_by(Incident.created_at.desc())
        .limit(3)
        .all()
    )
    for inc in incidents:
        icon = "🔥" if inc.severity == "critical" else "📋"
        notifications.append({
            "icon": icon,
            "title": f"事件: {inc.title}",
            "time": _relative_time(inc.created_at, now),
            "route": "incident",
            "severity": inc.severity or "warning",
        })

    offline_assets = (
        db.query(Asset)
        .filter(Asset.status != "online")
        .order_by(Asset.last_checked.desc().nullslast())
        .limit(3)
        .all()
    )
    for ast in offline_assets:
        notifications.append({
            "icon": "📉",
            "title": f"资产离线: {ast.name} ({ast.ip})",
            "time": _relative_time(ast.last_checked, now) if ast.last_checked else "未知",
            "route": "asset-list",
            "severity": "warning",
        })

    pending = (
        db.query(PendingAction)
        .filter(PendingAction.status == PendingAction.STATUS_PENDING)
        .order_by(PendingAction.created_at.desc())
        .limit(3)
        .all()
    )
    for pa in pending:
        notifications.append({
            "icon": "⏳",
            "title": f"待确认: {pa.title}",
            "time": _relative_time(pa.created_at, now),
            "route": "pending-actions",
            "severity": pa.risk_level or "medium",
        })

    alert_count = db.query(func.count(Alert.id)).filter(
        Alert.status.in_(["triggered", "firing"])
    ).scalar() or 0
    incident_count = db.query(func.count(Incident.id)).filter(
        ~Incident.status.in_(["resolved", "closed"])
    ).scalar() or 0
    pending_count = db.query(func.count(PendingAction.id)).filter(
        PendingAction.status == PendingAction.STATUS_PENDING
    ).scalar() or 0
    total = int(alert_count) + int(incident_count) + int(pending_count)

    return {"notifications": notifications, "count": total}


def _relative_time(dt, now):
    """把 datetime 转成 'x 分钟前' / 'x 小时前' / 'x 天前'."""
    if not dt:
        return "未知"
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return "刚刚"
    if secs < 3600:
        return f"{secs // 60} 分钟前"
    if secs < 86400:
        return f"{secs // 3600} 小时前"
    return f"{secs // 86400} 天前"


@router.get("/api/channels")
def api_channels_list(db: Session = Depends(get_db)):
    channels = notification_service.get_channels(db)
    return {
        "channels": [
            {
                "id": c.id, "name": c.name, "type": c.type, "config": c.config,
                "enabled": c.enabled,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in channels
        ],
    }


@router.post("/api/channels/create")
def api_channel_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    notification_service.create_channel(db, {
        "name": payload.get("name", ""),
        "type": payload.get("type", "email"),
        "config": payload.get("config", {}),
        "enabled": True,
    })
    return {"status": "ok"}


@router.delete("/api/channels/{channel_id}/delete")
def api_channel_delete(channel_id: int, db: Session = Depends(get_db)):
    notification_service.delete_channel(db, channel_id)
    return {"status": "ok"}


@router.get("/api/logs")
def api_logs_list(db: Session = Depends(get_db)):
    logs = notification_service.get_notification_logs(db)
    return {
        "logs": [
            {
                "id": lg.id, "alert_id": lg.alert_id, "channel_id": lg.channel_id,
                "channel_type": lg.channel_type, "recipient": lg.recipient,
                "title": lg.title, "success": lg.success, "error_message": lg.error_message,
                "created_at": lg.created_at.isoformat() if lg.created_at else None,
            }
            for lg in logs
        ],
    }
