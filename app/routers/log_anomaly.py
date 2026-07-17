from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.models import LogAnomalyRule

router = APIRouter(prefix="/log-anomaly", tags=["log_anomaly"])


class RuleBody(BaseModel):
    name: str
    source: str = ""
    keyword: Optional[str] = None
    regex_pattern: Optional[str] = None
    log_level: Optional[str] = None
    threshold: int = 5
    window_minutes: int = 10
    severity: str = "warning"
    enabled: bool = True


@router.get("/rules")
def list_rules(db: Session = Depends(get_db)):
    """列出所有日志异常检测规则"""
    rules = db.query(LogAnomalyRule).all()
    return {"rules": [
        {
            "id": r.id, "name": r.name, "source": r.source,
            "keyword": r.keyword, "regex_pattern": r.regex_pattern,
            "log_level": r.log_level,
            "threshold": r.threshold, "window_minutes": r.window_minutes,
            "severity": r.severity, "enabled": r.enabled,
        }
        for r in rules
    ]}


@router.post("/rules")
def create_rule(body: RuleBody, db: Session = Depends(get_db)):
    """创建日志异常检测规则"""
    try:
        rule = LogAnomalyRule(
            name=body.name, source=body.source, keyword=body.keyword,
            regex_pattern=body.regex_pattern, log_level=body.log_level or "",
            threshold=body.threshold,
            window_minutes=body.window_minutes, severity=body.severity,
            enabled=body.enabled,
        )
        db.add(rule)
        db.commit()
        return {"ok": True, "id": rule.id}
    except Exception as e:
        from app.logger import logger
        logger.error(f"log-anomaly create failed: {e}")
        return JSONResponse({"error": "创建失败"}, status_code=500)


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleBody, db: Session = Depends(get_db)):
    """更新日志异常检测规则"""
    try:
        rule = db.query(LogAnomalyRule).filter(LogAnomalyRule.id == rule_id).first()
        if not rule:
            return JSONResponse({"error": "规则不存在"}, status_code=404)
        rule.name = body.name
        rule.source = body.source
        rule.keyword = body.keyword
        rule.regex_pattern = body.regex_pattern
        rule.log_level = body.log_level or ""
        rule.threshold = body.threshold
        rule.window_minutes = body.window_minutes
        rule.severity = body.severity
        rule.enabled = body.enabled
        db.commit()
        return {"ok": True}
    except Exception as e:
        from app.logger import logger
        logger.error(f"log-anomaly update failed: {e}")
        return JSONResponse({"error": "更新失败"}, status_code=500)


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    """删除日志异常检测规则"""
    try:
        rule = db.query(LogAnomalyRule).filter(LogAnomalyRule.id == rule_id).first()
        if not rule:
            return JSONResponse({"error": "规则不存在"}, status_code=404)
        db.delete(rule)
        db.commit()
        return {"ok": True}
    except Exception as e:
        from app.logger import logger
        logger.error(f"log-anomaly delete failed: {e}")
        return JSONResponse({"error": "删除失败"}, status_code=500)
