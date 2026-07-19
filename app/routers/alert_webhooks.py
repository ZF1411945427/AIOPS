import json
import urllib.request
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AlertWebhook
from app.template_utils import get_templates
from app.security import validate_url_scheme
from app.logger import logger

router = APIRouter(prefix="/alert-webhooks", tags=["alert_webhooks"])
templates = get_templates()


def call_alert_webhooks(db: Session, alert):
    hooks = db.query(AlertWebhook).filter(AlertWebhook.enabled == True).all()
    for h in hooks:
        # SSRF 防护：仅允许 http/https 协议
        ok, reason = validate_url_scheme(h.url or "")
        if not ok:
            logger.warning(f"告警 webhook URL 校验失败 ({h.url}): {reason}")
            continue
        payload = json.dumps({
            "event": "alert",
            "alert_id": alert.id,
            "metric_name": alert.metric_name,
            "severity": alert.severity,
            "status": alert.status,
            "actual_value": alert.actual_value,
            "threshold": alert.threshold,
            "message": alert.message,
            "created_at": str(alert.created_at),
        }).encode()
        for attempt in range(h.retry_count):
            try:
                req = urllib.request.Request(h.url, payload, {"Content-Type": "application/json"})
                if h.secret:
                    req.add_header("Authorization", f"Bearer {h.secret}")
                urllib.request.urlopen(req, timeout=h.timeout)
                break
            except Exception:
                pass


@router.get("/status")
def status():
    return {"module": "alert_webhooks", "status": "ok"}
