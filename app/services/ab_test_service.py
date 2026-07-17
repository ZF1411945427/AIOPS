import json
import hashlib
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, Integer, Float
from app.models import ABTestConfig, ABTestRecord, AIProvider


def create_test(db: Session, data: dict) -> int:
    cfg = ABTestConfig(**data)
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg.id


def list_tests(db: Session, status: str = "") -> list:
    q = db.query(ABTestConfig)
    if status:
        q = q.filter(ABTestConfig.status == status)
    return q.order_by(ABTestConfig.created_at.desc()).all()


def get_test(test_id: int, db: Session):
    return db.query(ABTestConfig).filter(ABTestConfig.id == test_id).first()


def update_test(test_id: int, data: dict, db: Session):
    cfg = get_test(test_id, db)
    if not cfg:
        return None
    for k, v in data.items():
        setattr(cfg, k, v)
    db.commit()
    return cfg


def get_provider_for_request(test_id: int, session_id: int = None, db: Session = None) -> tuple:
    """根据 A/B 测试配置决定走哪个 provider。返回 (provider_id, group, test_config)"""
    cfg = db.query(ABTestConfig).filter(
        ABTestConfig.id == test_id,
        ABTestConfig.status == "active"
    ).first()
    if not cfg:
        return None, None, None

    h = hashlib.md5(f"{test_id}:{session_id or ''}".encode()).hexdigest()
    bucket = int(h[:8], 16) % 100
    ratio_a = int(cfg.split_ratio.split("/")[0])
    group = "a" if bucket < ratio_a else "b"

    if group == "a":
        return cfg.provider_a_id, group, cfg
    else:
        return cfg.provider_b_id, group, cfg


def record_result(
    db: Session,
    test_id: int,
    session_id: int = None,
    group: str = "a",
    provider_id: int = None,
    model_name: str = "",
    latency_ms: int = 0,
    token_count: int = 0,
    success: bool = True,
    user_feedback: str = "",
) -> int:
    rec = ABTestRecord(
        test_id=test_id,
        session_id=session_id,
        group=group,
        provider_id=provider_id,
        model_name=model_name,
        latency_ms=latency_ms,
        token_count=token_count,
        is_success=success,
        user_feedback=user_feedback,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec.id


def get_test_results(test_id: int, db: Session) -> dict:
    records = db.query(ABTestRecord).filter(ABTestRecord.test_id == test_id).all()
    if not records:
        return {"total": 0, "group_a": {}, "group_b": {}}

    a_records = [r for r in records if r.group == "a"]
    b_records = [r for r in records if r.group == "b"]

    def summarize(recs):
        if not recs:
            return {}
        total = len(recs)
        successes = sum(1 for r in recs if r.is_success)
        latencies = [r.latency_ms for r in recs if r.latency_ms]
        tokens = [r.token_count for r in recs if r.token_count]
        return {
            "total": total,
            "is_success": successes,
            "success_rate": round(successes / max(total, 1) * 100, 1),
            "avg_latency_ms": round(sum(latencies) / max(len(latencies), 1), 1) if latencies else 0,
            "avg_tokens": round(sum(tokens) / max(len(tokens), 1), 1) if tokens else 0,
        }

    return {
        "total": len(records),
        "group_a": summarize(a_records),
        "group_b": summarize(b_records),
        "winner": _compare(summarize(a_records), summarize(b_records)),
    }


def _compare(a: dict, b: dict) -> str:
    if not a or not b:
        return "insufficient_data"
    a_score = a.get("success_rate", 0) - (a.get("avg_latency_ms", 0) / 1000)
    b_score = b.get("success_rate", 0) - (b.get("avg_latency_ms", 0) / 1000)
    if a_score > b_score + 5:
        return "a"
    elif b_score > a_score + 5:
        return "b"
    return "inconclusive"
