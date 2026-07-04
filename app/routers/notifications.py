from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.template_utils import get_templates
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from datetime import datetime, timedelta

from app.database import get_db
from app.services import notification_service
from app.models import Alert, Asset, Incident, PendingAction

router = APIRouter(prefix="/notifications", tags=["notifications"])
templates = get_templates()


@router.get("/api/recent")
def recent_notifications(db: Session = Depends(get_db)):
    """实时聚合系统通知，供顶栏铃铛拉取。

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

    # 1. 未处理告警（按 severity critical>warning 排序，最近24h）
    alerts = (
        db.query(Alert)
        .filter(Alert.status.in_(["triggered", "firing"]))
        .filter(Alert.created_at >= day_ago)
        .order_by(
            # critical 优先（用 case 排序），再按时间倒序
            case((Alert.severity == "critical", 0), else_=1),
            Alert.created_at.desc(),
        )
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

    # 2. 未解决事件
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

    # 3. 离线资产
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

    # 4. 待确认AI动作
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

    # 未读总数 = 未处理告警 + 未解决事件 + 待确认动作
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


@router.get("", response_class=HTMLResponse)
def notification_page(request: Request, db: Session = Depends(get_db)):
    channels = notification_service.get_channels(db)
    logs = notification_service.get_notification_logs(db)
    return templates.TemplateResponse("notifications.html", {
        "request": request,
        "channels": channels,
        "logs": logs,
    })


@router.post("/channels/create")
def create_channel(
    name: str = Form(...),
    type: str = Form(...),
    config_host: str = Form(""),
    config_port: int = Form(587),
    config_user: str = Form(""),
    config_password: str = Form(""),
    config_recipients: str = Form(""),
    config_url: str = Form(""),
    config_webhook: str = Form(""),
    db: Session = Depends(get_db),
):
    config = {}
    if type == "email":
        config = {
            "host": config_host, "port": config_port,
            "user": config_user, "password": config_password,
            "recipients": config_recipients,
        }
    elif type == "webhook":
        config = {"url": config_url}
    elif type == "dingtalk":
        config = {"webhook": config_webhook}
    elif type == "wecom":
        config = {"webhook": config_webhook}
    notification_service.create_channel(db, {"name": name, "type": type, "config": config, "enabled": True})
    return RedirectResponse("/notifications", status_code=303)


@router.post("/channels/{channel_id}/delete")
def delete_channel(channel_id: int, db: Session = Depends(get_db)):
    notification_service.delete_channel(db, channel_id)
    return RedirectResponse("/notifications", status_code=303)


