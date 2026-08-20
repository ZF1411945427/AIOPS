"""告警风暴检测 API。

修复：原为空壳(仅 /status)。补全风暴状态查询（统计各规则近期告警密度与抑制情况）。
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.logger import logger
from app.models import Alert, AlertRule, AlertSuppression

router = APIRouter(prefix="/alert-storm", tags=["alert_storm"])


@router.get("/status")
def status():
    return {"module": "alert_storm", "status": "ok"}


@router.get("/api/current")
def current_storm(window_minutes: int = 1, threshold: int = 3, db: Session = Depends(get_db)):
    """查询当前疑似风暴的规则：近 window_minutes 分钟内告警数 >= threshold。

    返回逐规则告警密度 + 累计风暴抑制计数（AlertSuppression reason=storm）。
    """
    try:
        now = datetime.now()
        cutoff = now - timedelta(minutes=window_minutes)
        # 近窗口内各规则告警数
        counts = (
            db.query(Alert.rule_id, func.count(Alert.id).label("cnt"))
            .filter(Alert.created_at >= cutoff, Alert.archived == False)
            .group_by(Alert.rule_id)
            .all()
        )
        rule_map = {r.id: r for r in db.query(AlertRule).all()}
        storm_rules = []
        for rule_id, cnt in counts:
            if cnt >= threshold:
                rule = rule_map.get(rule_id)
                # 累计风暴抑制
                sup = db.query(AlertSuppression).filter(
                    AlertSuppression.rule_id == rule_id,
                    AlertSuppression.reason == "storm",
                ).order_by(AlertSuppression.id.desc()).first()
                storm_rules.append({
                    "rule_id": rule_id,
                    "rule_name": rule.name if rule else f"#{rule_id}",
                    "metric_name": rule.metric_name if rule else "",
                    "severity": rule.severity if rule else "warning",
                    "alert_count_in_window": cnt,
                    "suppressed_count": sup.suppressed_count if sup else 0,
                })

        # 汇总
        total_in_window = sum(cnt for _, cnt in counts)
        return {
            "window_minutes": window_minutes,
            "threshold": threshold,
            "total_alerts_in_window": total_in_window,
            "storm_rule_count": len(storm_rules),
            "storm_rules": storm_rules,
            "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as e:
        logger.warning(f"current_storm 异常: {e}")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.get("/api/suppressions")
def list_suppressions(limit: int = 100, db: Session = Depends(get_db)):
    """查询告警抑制记录（storm / dedup 两类）。"""
    try:
        rows = (
            db.query(AlertSuppression)
            .order_by(AlertSuppression.id.desc())
            .limit(limit)
            .all()
        )
        items = [{
            "id": s.id,
            "rule_id": s.rule_id,
            "rule_name": s.rule_name,
            "metric_name": s.metric_name,
            "suppressed_count": s.suppressed_count,
            "reason": s.reason,
            "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else None,
        } for s in rows]
        return {"items": items, "count": len(items)}
    except Exception as e:
        logger.warning(f"list_suppressions 异常: {e}")
        return {"items": [], "count": 0, "warning": str(e)}
