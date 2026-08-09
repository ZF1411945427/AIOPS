import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

from sqlalchemy.orm import Session
from app.models import NotificationChannel, NotificationLog, Alert
from app.security import validate_url_scheme


def get_channels(db: Session):
    return db.query(NotificationChannel).order_by(NotificationChannel.id.desc()).all()


def create_channel(db: Session, data: dict):
    # 兼容 config / channel_config 两种字段名
    if "config" in data and "channel_config" not in data:
        cfg = data.pop("config")
        data["channel_config"] = json.dumps(cfg, ensure_ascii=False) if isinstance(cfg, dict) else cfg
    elif isinstance(data.get("channel_config"), dict):
        data["channel_config"] = json.dumps(data["channel_config"], ensure_ascii=False)
    channel = NotificationChannel(**data)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def delete_channel(db: Session, channel_id: int):
    db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).delete()
    db.commit()


def update_channel(db: Session, channel_id: int, data: dict):
    ch = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if not ch:
        return None
    if "name" in data:
        ch.name = data["name"]
    if "type" in data:
        ch.type = data["type"]
    if "config" in data:
        existing = json.loads(ch.channel_config) if ch.channel_config else {}
        merged = dict(existing)
        for k, v in data["config"].items():
            if v == "" and k in ("password", "secret", "token", "webhook_secret"):
                continue
            merged[k] = v
        ch.channel_config = json.dumps(merged, ensure_ascii=False)
    db.commit()
    db.refresh(ch)
    return ch


def test_channel(db: Session, channel_id: int) -> tuple[bool, str]:
    ch = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if not ch:
        return False, "渠道不存在"
    config = json.loads(ch.channel_config) if ch.channel_config else {}
    title = "[AIOPS] 测试通知"
    content = "这是一条测试消息，您的通知渠道配置正确。"

    if ch.type == "email":
        return send_email(config, title, content)
    elif ch.type == "webhook":
        url = config.get("url", "")
        ok, reason = validate_url_scheme(url)
        if not ok:
            return False, f"URL 校验失败: {reason}"
        try:
            import urllib.request
            data = json.dumps({"title": title, "content": content}).encode()
            req = urllib.request.Request(url, data, {"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
            return True, ""
        except Exception as e:
            return False, str(e)
    elif ch.type in ("dingtalk", "wecom", "feishu"):
        webhook = config.get("webhook", "")
        ok, reason = validate_url_scheme(webhook)
        if not ok:
            return False, f"URL 校验失败: {reason}"
        try:
            import urllib.request
            if ch.type == "feishu":
                payload = {"msg_type": "text", "content": {"text": f"{title}\n{content}"}}
            else:
                payload = {"msgtype": "text", "text": {"content": f"{title}\n{content}"}}
            data = json.dumps(payload).encode()
            req = urllib.request.Request(webhook, data, {"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
            return True, ""
        except Exception as e:
            return False, str(e)
    elif ch.type == "log":
        return True, ""
    return False, "不支持测试的渠道类型"


def set_channel_enabled(db: Session, channel_id: int, enabled: bool):
    ch = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if not ch:
        return None
    ch.enabled = bool(enabled)
    db.commit()
    db.refresh(ch)
    return ch


def send_email(config: dict, title: str, content: str) -> tuple[bool, str]:
    try:
        host = config.get("host", "")
        port = config.get("port", 587)
        user = config.get("user", "")
        password = config.get("password", "")
        recipients = config.get("recipients", "").split(",")

        msg = MIMEText(content, "plain", "utf-8")
        msg["Subject"] = title
        msg["From"] = user
        msg["To"] = ", ".join(recipients)

        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, recipients, msg.as_string())
        return True, ""
    except Exception as e:
        return False, str(e)


def send_notification(db: Session, alert: Alert, channel: NotificationChannel) -> NotificationLog:
    config = json.loads(channel.channel_config) if channel.channel_config else {}
    title = f"[AIOPS] 告警: {alert.metric_name} - {alert.severity}"
    content = (
        f"告警ID: {alert.id}\n"
        f"指标: {alert.metric_name}\n"
        f"当前值: {alert.actual_value}\n"
        f"阈值: {alert.threshold}\n"
        f"级别: {alert.severity}\n"
        f"消息: {alert.message}\n"
        f"时间: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    success, error = False, "未知渠道类型"
    recipient = ""

    if channel.type == "email":
        recipient = config.get("user", "")
        success, error = send_email(config, title, content)
    elif channel.type == "webhook":
        recipient = config.get("url", "")
        ok, reason = validate_url_scheme(recipient)
        if not ok:
            success, error = False, f"URL 校验失败: {reason}"
        else:
            try:
                import urllib.request
                data = json.dumps({"title": title, "content": content, "alert_id": alert.id}).encode()
                req = urllib.request.Request(recipient, data, {"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=10)
                success, error = True, ""
            except Exception as e:
                success, error = False, str(e)
    elif channel.type in ("dingtalk", "wecom", "feishu"):
        recipient = config.get("webhook", "")
        ok, reason = validate_url_scheme(recipient)
        if not ok:
            success, error = False, f"URL 校验失败: {reason}"
        else:
            try:
                import urllib.request
                if channel.type == "feishu":
                    payload = {"msg_type": "text", "content": {"text": f"{title}\n{content}"}}
                else:
                    payload = {"msgtype": "text", "text": {"content": f"{title}\n{content}"}}
                data = json.dumps(payload).encode()
                req = urllib.request.Request(recipient, data, {"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=10)
                success, error = True, ""
            except Exception as e:
                success, error = False, str(e)
    elif channel.type == "log":
        recipient = "console"
        success, error = True, ""

    log = NotificationLog(
        alert_id=alert.id,
        channel_id=channel.id,
        channel_type=channel.type,
        recipient=recipient,
        title=title,
        notification_content=content,
        is_success=success,
        error_message=error,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def notify_new_alerts(db: Session, new_alerts: list[Alert]):
    channels = db.query(NotificationChannel).filter(NotificationChannel.enabled == True).all()
    for alert in new_alerts:
        for channel in channels:
            send_notification(db, alert, channel)


def get_notification_logs(db: Session, limit: int = 50):
    return db.query(NotificationLog).order_by(NotificationLog.created_at.desc()).limit(limit).all()


def get_notification_logs_for_alert(db: Session, alert_id: int):
    return db.query(NotificationLog).filter(NotificationLog.alert_id == alert_id).order_by(NotificationLog.created_at.desc()).all()


