"""告警静默 API（含定时静默调度）。

修复：原为空壳(仅 /status)。补全静默记录 CRUD + 定时静默调度 CRUD。
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.logger import logger
from app.models import AlertSilence, AlertSilenceSchedule

router = APIRouter(prefix="/alert-silence", tags=["alert_silence"])


def _silence_to_dict(s) -> dict:
    return {
        "id": s.id,
        "rule_id": s.rule_id,
        "expires_at": s.expires_at.strftime("%Y-%m-%d %H:%M:%S") if s.expires_at else None,
        "reason": s.reason,
        "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else None,
    }


def _schedule_to_dict(s) -> dict:
    return {
        "id": s.id,
        "rule_id": s.rule_id,
        "metric_name": s.metric_name,
        "asset_id": s.asset_id,
        "cron_expr": s.cron_expr,
        "duration_minutes": s.duration_minutes,
        "reason": s.reason,
        "enabled": bool(s.enabled),
        "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else None,
    }


@router.get("/status")
def status():
    return {"module": "alert_silence", "status": "ok"}


@router.get("/api/list")
def list_silences(active_only: bool = False, limit: int = 100, db: Session = Depends(get_db)):
    """查询告警静默记录。active_only=True 仅返回未过期。"""
    try:
        q = db.query(AlertSilence).order_by(AlertSilence.id.desc()).limit(limit)
        rows = q.all()
        items = [_silence_to_dict(s) for s in rows]
        if active_only:
            from datetime import datetime
            now = datetime.now()
            items = [i for i in items if i["expires_at"] and i["expires_at"] > now.strftime("%Y-%m-%d %H:%M:%S")]
        return {"items": items, "count": len(items)}
    except Exception as e:
        logger.warning(f"list_silences 异常: {e}")
        return {"items": [], "count": 0, "warning": str(e)}


@router.post("/api/create")
def create_silence(payload: dict, db: Session = Depends(get_db)):
    """创建静默：rule_id (可选) + expires_at + reason。"""
    try:
        from datetime import datetime, timedelta
        rule_id = payload.get("rule_id")
        reason = payload.get("reason", "")
        hours = int(payload.get("hours", 2))
        expires_at = datetime.now() + timedelta(hours=hours)
        s = AlertSilence(rule_id=rule_id, expires_at=expires_at, reason=reason)
        db.add(s)
        db.commit()
        db.refresh(s)
        return {"ok": True, "silence": _silence_to_dict(s)}
    except Exception as e:
        logger.warning(f"create_silence 异常: {e}")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)


@router.post("/api/{silence_id}/cancel")
def cancel_silence(silence_id: int, db: Session = Depends(get_db)):
    """取消静默：删除记录。"""
    try:
        s = db.query(AlertSilence).filter(AlertSilence.id == silence_id).first()
        if not s:
            return JSONResponse({"ok": False, "message": "静默不存在"}, status_code=404)
        db.delete(s)
        db.commit()
        return {"ok": True}
    except Exception as e:
        logger.warning(f"cancel_silence 异常: {e}")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)


# ── 定时静默调度 CRUD ──
@router.get("/api/schedules")
def list_schedules(db: Session = Depends(get_db)):
    """查询定时静默调度。"""
    try:
        rows = db.query(AlertSilenceSchedule).order_by(AlertSilenceSchedule.id.desc()).all()
        return {"items": [_schedule_to_dict(s) for s in rows], "count": len(rows)}
    except Exception as e:
        logger.warning(f"list_schedules 异常: {e}")
        return {"items": [], "count": 0, "warning": str(e)}


@router.post("/api/schedules/create")
def create_schedule(payload: dict, db: Session = Depends(get_db)):
    """创建定时静默调度：cron_expr + duration_minutes + (rule_id/metric_name/asset_id)。"""
    try:
        cron_expr = payload.get("cron_expr") or "0 2 * * 0"
        duration_minutes = int(payload.get("duration_minutes") or 120)
        s = AlertSilenceSchedule(
            rule_id=payload.get("rule_id"),
            metric_name=payload.get("metric_name", ""),
            asset_id=payload.get("asset_id"),
            cron_expr=cron_expr,
            duration_minutes=duration_minutes,
            reason=payload.get("reason", ""),
            enabled=bool(payload.get("enabled", True)),
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return {"ok": True, "schedule": _schedule_to_dict(s)}
    except Exception as e:
        logger.warning(f"create_schedule 异常: {e}")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)


@router.post("/api/schedules/{schedule_id}/update")
def update_schedule(schedule_id: int, payload: dict, db: Session = Depends(get_db)):
    """更新定时静默调度。"""
    try:
        s = db.query(AlertSilenceSchedule).filter(AlertSilenceSchedule.id == schedule_id).first()
        if not s:
            return JSONResponse({"ok": False, "message": "调度不存在"}, status_code=404)
        for field in ["rule_id", "metric_name", "asset_id", "cron_expr", "duration_minutes", "reason"]:
            if field in payload:
                setattr(s, field, payload[field])
        if "enabled" in payload:
            s.enabled = bool(payload["enabled"])
        db.commit()
        db.refresh(s)
        return {"ok": True, "schedule": _schedule_to_dict(s)}
    except Exception as e:
        logger.warning(f"update_schedule 异常: {e}")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)


@router.post("/api/schedules/{schedule_id}/delete")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """删除定时静默调度。"""
    try:
        s = db.query(AlertSilenceSchedule).filter(AlertSilenceSchedule.id == schedule_id).first()
        if not s:
            return JSONResponse({"ok": False, "message": "调度不存在"}, status_code=404)
        db.delete(s)
        db.commit()
        return {"ok": True}
    except Exception as e:
        logger.warning(f"delete_schedule 异常: {e}")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
