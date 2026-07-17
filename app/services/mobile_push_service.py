import os
import json
import time
import hmac
import base64
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import requests
from sqlalchemy.orm import Session

from app.models import MobileDevice, PushRecord, SystemConfig, Alert, PendingAction

logger = logging.getLogger("mobile_push")

from app.config import MOBILE_JWT_SECRET
_BIOMETRIC_SECRET = MOBILE_JWT_SECRET
_BIOMETRIC_TTL_DAYS = 7

_GETUI_BASE = "https://restapi.getui.com/v2"


def _get_getui_config(db: Session) -> Dict[str, str]:
    rows = db.query(SystemConfig).filter(
        SystemConfig.key.in_(["getui_app_id", "getui_app_key", "getui_master_secret"])
    ).all()
    cfg = {r.key: (r.config_value or "").strip() for r in rows}
    return cfg


def sign_request(params: Dict[str, Any], secret: str) -> str:
    raw = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _get_getui_token(db: Session, cfg: Dict[str, str]) -> Optional[str]:
    app_key = cfg.get("getui_app_key", "")
    master_secret = cfg.get("getui_master_secret", "")
    app_id = cfg.get("getui_app_id", "")
    if not app_key or not master_secret or not app_id:
        return None
    timestamp = str(int(time.time() * 1000))
    sign = hashlib.sha256((app_key + timestamp + master_secret).encode("utf-8")).digest()
    sign_b64 = base64.b64encode(sign).decode("utf-8")
    try:
        resp = requests.post(
            f"{_GETUI_BASE}/{app_id}/auth",
            json={"sign": sign_b64, "timestamp": timestamp, "appkey": app_key},
            timeout=10,
            proxies={"http": None, "https": None},
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            return data.get("token")
    except Exception as e:
        logger.warning("获取个推 token 失败: %s", e)
    return None


def _push_single_getui(cfg: Dict[str, str], token: str, push_token: str, title: str, body: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    app_id = cfg.get("getui_app_id", "")
    message = {
        "notification": {
            "title": title,
            "body": body or "",
            "click_type": "payload",
            "payload": json.dumps(payload, ensure_ascii=False),
        },
        "cid": push_token,
    }
    try:
        resp = requests.post(
            f"{_GETUI_BASE}/{app_id}/push/single/cid",
            headers={"Content-Type": "application/json", "token": token},
            json={"request_id": str(int(time.time() * 1000)), "audience": {"cid": [push_token]}, "push_message": message},
            timeout=10,
            proxies={"http": None, "https": None},
        )
        data = resp.json()
        return {"ok": data.get("code") == 0, "msg_id": (data.get("data") or {}).get("taskid") or (data.get("data") or {}).get("msg_id"), "error": data.get("msg")}
    except Exception as e:
        return {"ok": False, "msg_id": None, "error": str(e)}


def register_device(db: Session, user_id: int, device_id: str, platform: str, push_token: str, app_version: str = "") -> MobileDevice:
    device_id = (device_id or "").strip()
    platform = (platform or "").strip().lower()
    if not device_id:
        raise ValueError("device_id 不能为空")
    if platform not in ("ios", "android"):
        raise ValueError("platform 仅支持 ios / android")
    dev = db.query(MobileDevice).filter(
        MobileDevice.user_id == user_id,
        MobileDevice.device_id == device_id,
    ).first()
    now = datetime.utcnow()
    if dev:
        dev.platform = platform
        if push_token is not None:
            dev.push_token = push_token
        if app_version:
            dev.app_version = app_version
        dev.last_active_at = now
    else:
        dev = MobileDevice(
            user_id=user_id,
            device_id=device_id,
            platform=platform,
            push_token=push_token or "",
            app_version=app_version or "",
            last_active_at=now,
        )
        db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def unregister_device(db: Session, user_id: int, device_id: str) -> bool:
    dev = db.query(MobileDevice).filter(
        MobileDevice.user_id == user_id,
        MobileDevice.device_id == device_id,
    ).first()
    if not dev:
        return False
    db.delete(dev)
    db.commit()
    return True


def send_push(db: Session, user_id: int, title: str, body: str, payload_dict: Optional[Dict[str, Any]] = None, push_type: str = "general", ref_id: Optional[int] = None) -> List[PushRecord]:
    devices = db.query(MobileDevice).filter(
        MobileDevice.user_id == user_id,
        MobileDevice.push_token != "",
        MobileDevice.push_token != None,
    ).all()
    if not devices:
        logger.info("用户 %s 无可用推送设备，跳过推送: %s", user_id, title)
        return []
    cfg = _get_getui_config(db)
    token = _get_getui_token(db, cfg) if cfg.get("getui_app_id") else None
    payload = payload_dict or {}
    records: List[PushRecord] = []
    now = datetime.utcnow()
    for dev in devices:
        rec = PushRecord(
            device_id=dev.id,
            title=title,
            body=body or "",
            payload=json.dumps(payload, ensure_ascii=False),
            type=push_type,
            ref_id=ref_id,
            status="pending",
            created_at=now,
        )
        if not cfg.get("getui_app_id"):
            rec.status = "skipped"
            rec.error = "未配置个推推送参数"
            logger.info("未配置个推推送参数，跳过发送: %s", title)
        elif not token:
            rec.status = "failed"
            rec.error = "获取个推 token 失败"
        else:
            result = _push_single_getui(cfg, token, dev.push_token or "", title, body or "", payload)
            rec.provider_msg_id = result.get("msg_id") or ""
            rec.sent_at = datetime.utcnow()
            if result.get("ok"):
                rec.status = "sent"
            else:
                rec.status = "failed"
                rec.error = result.get("error") or "推送失败"
        db.add(rec)
        records.append(rec)
    db.commit()
    return records


def notify_alert(db: Session, alert: Alert) -> List[PushRecord]:
    severity = (getattr(alert, "severity", "") or "warning").lower()
    title = f"[{alert.severity.upper()}] 告警: {alert.metric_name}"
    body = f"当前值 {alert.actual_value} / 阈值 {alert.threshold}\n{alert.message or ''}"
    payload = {
        "type": "alert",
        "ref_id": alert.id,
        "severity": severity,
        "metric_name": alert.metric_name,
        "asset_id": getattr(alert, "asset_id", None),
        "priority": "critical" if severity == "critical" else "normal",
    }
    push_type = "alert_critical" if severity == "critical" else "alert"
    return send_push(db, getattr(alert, "asset_id", None) or _alert_owner(db, alert.id), title, body, payload, push_type=push_type, ref_id=alert.id)


def _alert_owner(db: Session, alert_id: int) -> int:
    return 1


def notify_pending_action(db: Session, pending_action: PendingAction) -> List[PushRecord]:
    user_id = _pending_action_owner(db, pending_action)
    title = f"待确认动作: {pending_action.title or pending_action.action_type}"
    body = (pending_action.reason or "") + (f"\n风险等级: {pending_action.risk_level}" if pending_action.risk_level else "")
    payload = {
        "type": "pending_action",
        "ref_id": pending_action.id,
        "action_type": pending_action.action_type,
        "risk_level": pending_action.risk_level,
    }
    return send_push(db, user_id, title, body, payload, push_type="pending_action", ref_id=pending_action.id)


def _pending_action_owner(db: Session, pa: PendingAction) -> int:
    if pa.session_id:
        from app.models import ChatSession
        sess = db.query(ChatSession).filter(ChatSession.id == pa.session_id).first()
        if sess:
            return sess.user_id
    return 1


def notify_workflow_event(db: Session, run_id: int, event_type: str) -> List[PushRecord]:
    title = f"工作流事件: {event_type}"
    body = f"运行 ID: {run_id}\n事件: {event_type}"
    payload = {"type": "workflow_event", "ref_id": run_id, "event_type": event_type}
    return send_push(db, 1, title, body, payload, push_type="workflow", ref_id=run_id)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def issue_biometric_token(user_id: int, device_id: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "user_id": user_id,
        "device_id": device_id,
        "iat": now,
        "exp": now + _BIOMETRIC_TTL_DAYS * 86400,
    }
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h}.{p}".encode("utf-8")
    sig = hmac.new(_BIOMETRIC_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    s = _b64url_encode(sig)
    return f"{h}.{p}.{s}"


def verify_biometric_token(token: str) -> Optional[Dict[str, Any]]:
    if not token or token.count(".") != 2:
        return None
    h, p, s = token.split(".")
    signing_input = f"{h}.{p}".encode("utf-8")
    expected_sig = hmac.new(_BIOMETRIC_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        provided_sig = _b64url_decode(s)
    except Exception:
        return None
    if not hmac.compare_digest(expected_sig, provided_sig):
        return None
    try:
        payload = json.loads(_b64url_decode(p).decode("utf-8"))
    except Exception:
        return None
    if payload.get("exp") and int(time.time()) > int(payload["exp"]):
        return None
    return payload


def issue_login_token(user_id: int, username: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "user_id": user_id,
        "username": username,
        "iat": now,
        "exp": now + _BIOMETRIC_TTL_DAYS * 86400,
        "type": "login",
    }
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h}.{p}".encode("utf-8")
    sig = hmac.new(_BIOMETRIC_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    s = _b64url_encode(sig)
    return f"{h}.{p}.{s}"


def verify_login_token(token: str) -> Optional[Dict[str, Any]]:
    if not token or token.count(".") != 2:
        return None
    h, p, s = token.split(".")
    signing_input = f"{h}.{p}".encode("utf-8")
    expected_sig = hmac.new(_BIOMETRIC_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        provided_sig = _b64url_decode(s)
    except Exception:
        return None
    if not hmac.compare_digest(expected_sig, provided_sig):
        return None
    try:
        payload = json.loads(_b64url_decode(p).decode("utf-8"))
    except Exception:
        return None
    if payload.get("type") != "login":
        return None
    if payload.get("exp") and int(time.time()) > int(payload["exp"]):
        return None
    return payload
