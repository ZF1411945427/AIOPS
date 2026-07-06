import os
import uuid
import base64
import json
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    User, Asset, Alert, OnCallSchedule, WorkflowRun, AgentWorkflowRun,
    MobileDevice, PushRecord, CheckinRecord, AIProvider, AgentConfig,
)
from app.services.mobile_push_service import (
    register_device, unregister_device, send_push,
    issue_biometric_token, verify_biometric_token,
    issue_login_token, verify_login_token,
)
from app.services.agent_service import call_llm

router = APIRouter(prefix="/mobile", tags=["mobile"])

_CHECKIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "checkin")


def require_user(request: Request, db: Session = Depends(get_db)) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            payload = verify_login_token(auth[7:])
            if payload:
                user_id = payload.get("user_id")
                request.session["user_id"] = user_id
                request.session["username"] = payload.get("username", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")
    return user_id


def _is_admin(db: Session, user_id: int) -> bool:
    u = db.query(User).filter(User.id == user_id).first()
    return bool(u and u.role == "admin")


class PushRegisterBody(BaseModel):
    device_id: str
    platform: str
    push_token: str = ""
    app_version: str = ""


class PushUnregisterBody(BaseModel):
    device_id: str


class BiometricIssueBody(BaseModel):
    device_id: str


class BiometricLoginBody(BaseModel):
    biometric_token: str


class VisionDiagnoseBody(BaseModel):
    image_base64: str
    asset_id: Optional[int] = None


class CheckinBody(BaseModel):
    asset_id: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: str = ""
    photo_base64: str = ""
    note: str = ""


def _device_to_dict(d: MobileDevice) -> dict:
    return {
        "id": d.id,
        "user_id": d.user_id,
        "device_id": d.device_id,
        "platform": d.platform,
        "app_version": d.app_version or "",
        "last_active_at": d.last_active_at.strftime("%Y-%m-%d %H:%M:%S") if d.last_active_at else None,
        "created_at": d.created_at.strftime("%Y-%m-%d %H:%M:%S") if d.created_at else None,
        "has_push_token": bool(d.push_token),
        "has_biometric": bool(d.biometric_token),
    }


def _push_record_to_dict(r: PushRecord) -> dict:
    return {
        "id": r.id,
        "device_id": r.device_id,
        "title": r.title,
        "body": r.body or "",
        "payload": r.payload or "",
        "type": r.type or "",
        "ref_id": r.ref_id,
        "status": r.status or "",
        "provider_msg_id": r.provider_msg_id or "",
        "error": r.error or "",
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
        "sent_at": r.sent_at.strftime("%Y-%m-%d %H:%M:%S") if r.sent_at else None,
    }


@router.post("/push/register")
def push_register(body: PushRegisterBody, user_id: int = Depends(require_user), db: Session = Depends(get_db)):
    try:
        dev = register_device(db, user_id, body.device_id, body.platform, body.push_token, body.app_version)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return {"ok": True, "id": dev.id, "device_id": dev.device_id}


@router.post("/push/unregister")
def push_unregister(body: PushUnregisterBody, user_id: int = Depends(require_user), db: Session = Depends(get_db)):
    ok = unregister_device(db, user_id, body.device_id)
    return {"ok": ok}


@router.post("/auth/biometric/issue")
def biometric_issue(body: BiometricIssueBody, user_id: int = Depends(require_user), db: Session = Depends(get_db)):
    device_id = (body.device_id or "").strip()
    if not device_id:
        return JSONResponse({"ok": False, "error": "device_id 不能为空"}, status_code=400)
    token = issue_biometric_token(user_id, device_id)
    dev = db.query(MobileDevice).filter(
        MobileDevice.user_id == user_id, MobileDevice.device_id == device_id
    ).first()
    if dev:
        dev.biometric_token = token
        db.commit()
    else:
        dev = MobileDevice(
            user_id=user_id, device_id=device_id, platform="unknown",
            biometric_token=token, last_active_at=datetime.utcnow(),
        )
        db.add(dev)
        db.commit()
    return {"ok": True, "biometric_token": token, "expires_in_days": 7}


@router.post("/auth/biometric")
def biometric_login(body: BiometricLoginBody, request: Request, db: Session = Depends(get_db)):
    token = (body.biometric_token or "").strip()
    payload = verify_biometric_token(token)
    if not payload:
        return JSONResponse({"ok": False, "error": "生物识别 token 无效或已过期"}, status_code=401)
    user_id = payload.get("user_id")
    device_id = payload.get("device_id")
    dev = db.query(MobileDevice).filter(
        MobileDevice.user_id == user_id, MobileDevice.device_id == device_id
    ).first()
    if not dev or dev.biometric_token != token:
        return JSONResponse({"ok": False, "error": "设备未绑定或 token 已失效，请重新登录"}, status_code=401)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return JSONResponse({"ok": False, "error": "用户不存在"}, status_code=401)
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    return {"ok": True, "user_id": user.id, "username": user.username, "role": user.role}


@router.get("/scan/asset")
def scan_asset(code: str, user_id: int = Depends(require_user), db: Session = Depends(get_db)):
    code = (code or "").strip()
    if not code:
        return JSONResponse({"ok": False, "error": "code 不能为空"}, status_code=400)
    asset = db.query(Asset).filter(Asset.name == code).first()
    if not asset:
        asset = db.query(Asset).filter(Asset.tags.like(f"%{code}%")).first()
    if not asset:
        return JSONResponse({"ok": False, "error": "未找到匹配资产"}, status_code=404)
    return {
        "ok": True,
        "asset": {
            "id": asset.id,
            "name": asset.name,
            "type": asset.type,
            "ci_type": asset.ci_type or "",
            "ip": asset.ip or "",
            "status": asset.status or "",
            "tags": asset.tags or "",
            "k8s_cluster": asset.k8s_cluster or "",
            "last_checked": asset.last_checked.strftime("%Y-%m-%d %H:%M:%S") if asset.last_checked else None,
            "latency_ms": asset.latency_ms,
        },
    }


@router.post("/vision/diagnose")
def vision_diagnose(body: VisionDiagnoseBody, user_id: int = Depends(require_user), db: Session = Depends(get_db)):
    image_b64 = (body.image_base64 or "").strip()
    if not image_b64:
        return JSONResponse({"ok": False, "error": "image_base64 不能为空"}, status_code=400)
    if "," in image_b64 and image_b64.startswith("data:"):
        image_b64 = image_b64.split(",", 1)[1]
    cfg = db.query(AgentConfig).filter(AgentConfig.name == "default").first()
    if not cfg or not cfg.default_provider_id:
        return JSONResponse({"ok": False, "error": "未配置 AI 服务，无法进行图片识别"}, status_code=503)
    provider = db.query(AIProvider).filter(
        AIProvider.id == cfg.default_provider_id, AIProvider.is_enabled == True
    ).first()
    if not provider:
        return JSONResponse({"ok": False, "error": "AI 服务不可用"}, status_code=503)
    prompt = "这是服务器面板/告警屏照片，请识别指示灯状态（正常/告警/故障），判断可能故障类型，给出处置建议"
    asset_hint = ""
    if body.asset_id:
        asset = db.query(Asset).filter(Asset.id == body.asset_id).first()
        if asset:
            asset_hint = f"\n关联资产: {asset.name} ({asset.type}), IP: {asset.ip or '未知'}, 状态: {asset.status}"
    messages = [
        {"role": "user", "content": [
            {"type": "text", "text": prompt + asset_hint},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
        ]}
    ]
    try:
        result = call_llm(provider, messages, timeout_override=60)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"AI 服务调用异常: {e}"}, status_code=502)
    if result.get("error"):
        return JSONResponse({"ok": False, "error": "当前 AI 服务不支持图片识别或调用失败: " + str(result["error"])}, status_code=503)
    diagnosis = ""
    try:
        diagnosis = result["choices"][0]["message"]["content"] or ""
    except Exception:
        diagnosis = json.dumps(result, ensure_ascii=False)
    return {"ok": True, "diagnosis": diagnosis, "asset_id": body.asset_id}


@router.post("/checkin")
def checkin(body: CheckinBody, user_id: int = Depends(require_user), db: Session = Depends(get_db)):
    photo_path = ""
    if body.photo_base64:
        b64 = body.photo_base64.strip()
        if "," in b64 and b64.startswith("data:"):
            b64 = b64.split(",", 1)[1]
        try:
            raw = base64.b64decode(b64)
        except Exception:
            return JSONResponse({"ok": False, "error": "photo_base64 不是合法的 Base64"}, status_code=400)
        try:
            os.makedirs(_CHECKIN_DIR, exist_ok=True)
            fname = f"{user_id}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}.jpg"
            fpath = os.path.join(_CHECKIN_DIR, fname)
            with open(fpath, "wb") as f:
                f.write(raw)
            photo_path = f"/static/checkin/{fname}"
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"保存签到照片失败: {e}"}, status_code=500)
    rec = CheckinRecord(
        user_id=user_id,
        asset_id=body.asset_id,
        latitude=body.latitude,
        longitude=body.longitude,
        address=body.address or "",
        photo_path=photo_path,
        note=body.note or "",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return {"ok": True, "id": rec.id, "photo_path": photo_path, "created_at": rec.created_at.strftime("%Y-%m-%d %H:%M:%S") if rec.created_at else None}


@router.get("/dashboard")
def dashboard(user_id: int = Depends(require_user), db: Session = Depends(get_db)):
    from app.routers.system_posture import _build_systems, _process_system
    now = datetime.now()
    start = now - timedelta(days=30)
    systems = _build_systems(db)
    h = w = c = u = 0
    total_health = 0.0
    cnt = 0
    for sys in systems:
        r = _process_system(sys, db, start, now)
        if r:
            st = r.get("status", "unknown")
            total_health += float(r.get("sla_value", 0) or 0)
            cnt += 1
        else:
            st = "unknown"
        if st == "healthy":
            h += 1
        elif st == "warning":
            w += 1
        elif st == "critical":
            c += 1
        else:
            u += 1
    health = {
        "healthy": h, "warning": w, "critical": c, "unknown": u,
        "avg_sla": round(total_health / cnt, 2) if cnt else 0,
        "system_count": len(systems),
    }

    from app.services import alert_service
    try:
        alert_stats = alert_service.get_alert_stats(db)
    except Exception:
        alert_stats = {}

    oncalls = db.query(OnCallSchedule).filter(
        OnCallSchedule.current_period_start <= now,
        OnCallSchedule.current_period_end >= now,
    ).order_by(OnCallSchedule.team_name).all()
    oncall_list = [
        {
            "team_name": o.team_name,
            "current_oncall": o.current_oncall,
            "period_start": o.current_period_start.strftime("%Y-%m-%d %H:%M") if o.current_period_start else None,
            "period_end": o.current_period_end.strftime("%Y-%m-%d %H:%M") if o.current_period_end else None,
        }
        for o in oncalls
    ]

    running_sop = db.query(WorkflowRun).filter(WorkflowRun.status == WorkflowRun.STATUS_RUNNING).count()
    running_agent = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.status == AgentWorkflowRun.STATUS_RUNNING).count()
    workflows = {"running_sop": running_sop, "running_agent": running_agent}

    asset_total = db.query(Asset).count()
    asset_online = db.query(Asset).filter(Asset.status == "online").count()

    return {
        "health": health,
        "alerts": alert_stats,
        "oncall": {"items": oncall_list, "current_oncall": oncall_list[0]["current_oncall"] if oncall_list else None},
        "workflows": workflows,
        "assets": {"total": asset_total, "online": asset_online, "offline": asset_total - asset_online},
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.get("/devices")
def list_devices(user_id: int = Depends(require_user), db: Session = Depends(get_db)):
    admin = _is_admin(db, user_id)
    q = db.query(MobileDevice)
    if not admin:
        q = q.filter(MobileDevice.user_id == user_id)
    items = q.order_by(MobileDevice.last_active_at.desc().nullslast()).all()
    return {"items": [_device_to_dict(d) for d in items], "total": len(items), "is_admin": admin}


@router.delete("/devices/{device_id}")
def delete_device(device_id: int, user_id: int = Depends(require_user), db: Session = Depends(get_db)):
    dev = db.query(MobileDevice).filter(MobileDevice.id == device_id).first()
    if not dev:
        return JSONResponse({"ok": False, "error": "设备不存在"}, status_code=404)
    if not _is_admin(db, user_id) and dev.user_id != user_id:
        return JSONResponse({"ok": False, "error": "无权删除该设备"}, status_code=403)
    db.query(PushRecord).filter(PushRecord.device_id == dev.id).delete()
    db.delete(dev)
    db.commit()
    return {"ok": True}


@router.get("/push/logs")
def push_logs(user_id: int = Depends(require_user), db: Session = Depends(get_db)):
    admin = _is_admin(db, user_id)
    q = db.query(PushRecord).join(MobileDevice, PushRecord.device_id == MobileDevice.id)
    if not admin:
        q = q.filter(MobileDevice.user_id == user_id)
    items = q.order_by(PushRecord.created_at.desc()).limit(50).all()
    return {"items": [_push_record_to_dict(r) for r in items], "total": len(items), "is_admin": admin}
